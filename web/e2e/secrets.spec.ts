import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";

// V5 Secrets view: credentials appear within 5 seconds of being issued, count down, and a refused request is shown.
const OBSERVER = "http://localhost:8765";
const WEB = "http://localhost:8081";
const KUBECTL = ["--context", "k3d-ztp"];

const BILLING_ASKS = `
import json, urllib.request, urllib.error
from spiffe import WorkloadApiClient
def v(path, body=None, token=None):
    r = urllib.request.Request("http://vault.vault.svc:8200/v1/" + path, data=json.dumps(body).encode() if body else None,
                               headers={"X-Vault-Token": token} if token else {}, method="PUT" if body else "GET")
    return json.load(urllib.request.urlopen(r, timeout=5))
with WorkloadApiClient(socket_path="unix:///spiffe-workload-api/spire-agent.sock") as c:
    jwt = c.fetch_jwt_svid(audience={"vault"}).token
token = v("auth/jwt/login", {"role": "billing", "jwt": jwt})["auth"]["client_token"]
try:
    v("database/creds/records-api", token=token)
except urllib.error.HTTPError as e:
    print(e.code)
`;

test.afterEach(async ({ request }) => { await request.put(`${OBSERVER}/layers/secrets`, { data: { mode: "off" }, timeout: 60_000 }); });

test("a credential shows up within 5 seconds of being issued, and counts down", async ({ page, request }) => {
  test.setTimeout(120_000);
  // A restart empties records-api's credential cache, so the next request has to ask Vault for a new one.
  execFileSync("kubectl", [...KUBECTL, "-n", "clinic", "rollout", "restart", "deploy/records-api"]);
  execFileSync("kubectl", [...KUBECTL, "-n", "clinic", "rollout", "status", "deploy/records-api", "--timeout=90s"]);
  expect((await request.put(`${OBSERVER}/layers/secrets`, { data: { mode: "audit" }, timeout: 60_000 })).ok()).toBe(true);
  await page.goto("/#secrets");
  await page.waitForTimeout(4_000); // services poll the layer ConfigMap every 2 seconds
  expect((await request.get(`${WEB}/api/patients`)).status()).toBe(200);

  // The newest row is the first one. Close to the full 120 seconds left means it was issued moments ago, not backfilled.
  const left = page.getByRole("cell", { name: /seconds left/ }).first();
  const seconds = async () => Number(((await left.getAttribute("aria-label")) ?? "0").split(" ")[0]);
  await expect.poll(seconds, { timeout: 5_000 }).toBeGreaterThanOrEqual(112);
  await expect(page.getByRole("cell", { name: "records-api", exact: true }).first()).toBeVisible();
  const first = await seconds();
  expect(first).toBeLessThanOrEqual(120);
  await page.waitForTimeout(3_000);
  expect(await seconds()).toBeLessThan(first);
  await page.screenshot({ path: "e2e/screenshots/secrets.png" });
});

test("a service that may not read database credentials is shown as refused", async ({ page }) => {
  await page.goto("/#secrets");
  const status = execFileSync("kubectl", [...KUBECTL, "-n", "clinic", "exec", "-i", "deploy/billing", "--", "python", "-"],
    { input: BILLING_ASKS, encoding: "utf8" }).trim();
  expect(status).toBe("403");
  await expect(page.getByText("billing was refused a records-api database credential").first()).toBeVisible({ timeout: 5_000 });
});
