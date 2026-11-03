import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

const IDS = ["echo-a", "echo-b"].map((sa) => `spiffe://playground.local/ns/clinic/sa/${sa}`);

test("Identity view shows both workloads with a live countdown", async ({ page }) => {
  await page.goto("/#identity");
  for (const id of IDS) {
    await expect(page.getByLabel(`SPIFFE ID ${id}`)).toBeVisible({ timeout: 30_000 });
  }
  await expect(page.getByRole("status")).toHaveText(/Receiving events/);
  const card = page.locator("article", { hasText: "echo-a" });
  await expect(card.getByText("Identity valid")).toBeVisible();
  const first = await card.getByRole("figure").getAttribute("aria-label");
  await page.waitForTimeout(3000);
  expect(await card.getByRole("figure").getAttribute("aria-label")).not.toBe(first);
});

test("a rotation shows a new current serial at the top of the history", async ({ page }) => {
  await page.goto("/#identity");
  const card = page.locator("article", { hasText: "echo-a" });
  const current = card.locator("li.now .data").first();
  await expect(current).toHaveText(/^[0-9a-f]{8}$/, { timeout: 30_000 });
  // On load the dashboard replays old events, so the serial changes for a moment. Wait until it holds still.
  let last = "";
  await expect.poll(async () => { const t = (await current.textContent())!; const same = t === last; last = t; return same; },
    { intervals: [1000], timeout: 15_000 }).toBe(true);
  const before = last;
  // TTL is 2 minutes and SPIRE rotates at half-life, so a new serial lands within ~70s.
  await expect(current).not.toHaveText(before, { timeout: 100_000 });
});

for (const theme of ["light", "dark"] as const) {
  test(`screenshot, ${theme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/#identity");
    await expect(page.getByLabel(`SPIFFE ID ${IDS[0]}`)).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `e2e/screenshots/identity-${theme}.png`, fullPage: true });
  });
}

test("removing the registration leaves the identity to expire", async ({ page }) => {
  test.setTimeout(300_000);
  const kubectl = (...args: string[]) => execFileSync("kubectl", ["--context", "k3d-ztp", ...args], { cwd: ".." });
  await page.goto("/#identity");
  const card = page.locator("article", { hasText: "echo-b" });
  await expect(card.getByText("Identity valid")).toBeVisible({ timeout: 30_000 });
  try {
    kubectl("delete", "clusterspiffeid", "clinic");
    await expect(card.getByText("Registration removed")).toBeVisible({ timeout: 30_000 });
    // 2 minute TTL: with no registration the workload cannot renew, so the ring runs out.
    await expect(card.getByRole("figure")).toHaveAttribute("aria-label", "expired", { timeout: 180_000 });
    await page.screenshot({ path: "e2e/screenshots/identity-stale.png" });
  } finally {
    kubectl("apply", "-f", "deploy/spire/clusterspiffeid-clinic.yaml");
  }
  await expect(card.getByText("Identity valid")).toBeVisible({ timeout: 120_000 });
});
