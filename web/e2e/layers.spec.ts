import { expect, test, type Page } from "@playwright/test";

const OBSERVER = "http://localhost:8765";
const WEB = "http://localhost:8081";

const put = (page: Page, layer: string, mode: string) =>
  page.request.put(`${OBSERVER}/layers/${layer}`, { data: { mode } });
const reset = async (page: Page) => { await put(page, "user", "off"); await put(page, "secrets", "off"); await put(page, "network", "off"); await put(page, "mtls", "off"); await put(page, "identity", "off"); };
const mode = (page: Page, layer: string) => page.getByRole("radiogroup", { name: new RegExp(layer) }).getByRole("radio", { checked: true });

test.beforeEach(async ({ page }) => reset(page));
test.afterEach(async ({ page }) => reset(page));

test("each layer's current mode is visible, and changing it reaches the services within 5 seconds", async ({ page }) => {
  await page.goto("/#layers");
  await expect(mode(page, "Workload identity")).toHaveText("Off");
  await expect(mode(page, "Mutual TLS")).toHaveText("Off");

  await page.getByRole("radiogroup", { name: /Workload identity/ }).getByRole("radio", { name: "Audit" }).click();
  await expect(mode(page, "Workload identity")).toHaveText("Audit");
  await page.getByRole("radiogroup", { name: /Mutual TLS/ }).getByRole("radio", { name: "Audit" }).click();
  await expect(mode(page, "Mutual TLS")).toHaveText("Audit");
  await expect(page.getByText("a would-be refusal is logged")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/layers.png" });

  // The clinic's web service reports the modes it is acting on.
  await expect.poll(async () => (await (await page.request.get(`${WEB}/healthz`)).json()).modes, { timeout: 5_000 })
    .toMatchObject({ identity: "audit", mtls: "audit" });
});

test("mTLS enforce with identity off is refused, with the reason, and nothing changes", async ({ page }) => {
  await page.goto("/#layers");
  await page.getByRole("radiogroup", { name: /Mutual TLS/ }).getByRole("radio", { name: "Enforce" }).click();
  await expect(page.getByRole("alert")).toContainText("mTLS needs workload identity");
  await expect(mode(page, "Mutual TLS")).toHaveText("Off");
  expect(await (await page.request.get(`${OBSERVER}/layers`)).json()).toEqual({ identity: "off", mtls: "off", secrets: "off", user: "off", network: "off" });
});

test("network enforce stops the attacker reaching Postgres, and audit is not offered", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto("/#layers");
  const group = page.getByRole("radiogroup", { name: /Network policy/ });
  await expect(group.getByRole("radio", { name: "Audit" })).toBeDisabled();
  await expect(page.getByText("Not available: a dropped connection leaves no log")).toBeVisible();

  const attack = async () => (await (await page.request.post(`${OBSERVER}/attacks/read-postgres/run`, { timeout: 30_000 })).json()).evidence.outcome;
  expect(await attack()).toBe("succeeds");
  await group.getByRole("radio", { name: "Enforce" }).click();
  await expect(mode(page, "Network policy")).toHaveText("Enforce");
  await expect.poll(attack, { timeout: 5_000 + 20_000 }).toBe("blocked");

  await group.getByRole("radio", { name: "Off" }).click();
  await expect(mode(page, "Network policy")).toHaveText("Off");
  await expect.poll(attack, { timeout: 20_000 }).toBe("succeeds");
});

test("secrets enforce revokes the static password and the clinic still works, and off brings it back", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/#layers");
  const group = page.getByRole("radiogroup", { name: /Short-lived secrets/ });
  await expect(mode(page, "Short-lived secrets")).toHaveText("Off");
  await group.getByRole("radio", { name: "Enforce" }).click();
  await expect(mode(page, "Short-lived secrets")).toHaveText("Enforce", { timeout: 30_000 });
  await expect(page.getByText("a leaked copy no longer works")).toBeVisible();
  await expect.poll(async () => (await page.request.get(`${WEB}/api/patients`)).status(), { timeout: 10_000 }).toBe(200);

  await group.getByRole("radio", { name: "Off" }).click();
  await expect(mode(page, "Short-lived secrets")).toHaveText("Off", { timeout: 30_000 });
  await expect.poll(async () => (await page.request.get(`${WEB}/api/patients`)).status(), { timeout: 10_000 }).toBe(200);
});

test("the user layer changes from the page and the services pick it up within 5 seconds", async ({ page }) => {
  await page.goto("/#layers");
  const group = page.getByRole("radiogroup", { name: /User identity/ });
  await expect(mode(page, "User identity")).toHaveText("Off");
  await group.getByRole("radio", { name: "Audit" }).click();
  await expect(mode(page, "User identity")).toHaveText("Audit");
  await expect.poll(async () => (await (await page.request.get(`${WEB}/healthz`)).json()).modes, { timeout: 5_000 })
    .toMatchObject({ user: "audit" });
});
