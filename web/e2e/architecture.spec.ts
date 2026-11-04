import { expect, test, type Page } from "@playwright/test";

const OBSERVER = "http://localhost:8765";
const put = (page: Page, layer: string, mode: string) => page.request.put(`${OBSERVER}/layers/${layer}`, { data: { mode } });
const reset = async (page: Page) => { await put(page, "secrets", "off"); await put(page, "network", "off"); await put(page, "mtls", "off"); await put(page, "identity", "off"); };

test.beforeEach(async ({ page }) => reset(page));
test.afterEach(async ({ page }) => reset(page));

test("each layer names its pattern component and the unbuilt ones say so", async ({ page }) => {
  await page.goto("/#architecture");
  await expect(page.getByText("SPIFFE and SPIRE", { exact: true })).toBeVisible();
  await expect(page.getByText("HashiCorp Vault and External Secrets")).toBeVisible();
  await expect(page.getByLabel("User identity: Not built yet")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/architecture-off.png", fullPage: true });
});

test("flipping a layer on the Layers view updates the Architecture view within 5 seconds", async ({ page }) => {
  await page.goto("/#architecture");
  await expect(page.getByLabel("Mutual TLS and authorisation: Off")).toBeVisible();
  await put(page, "identity", "audit");
  await put(page, "mtls", "enforce");
  await expect(page.getByLabel("Mutual TLS and authorisation: Enforce")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText("checked and refused when not allowed").first()).toBeVisible();
  await expect(page.getByLabel("Network policy: Off")).toBeVisible();
  await put(page, "network", "enforce");
  await expect(page.getByLabel("Network policy: Enforce")).toBeVisible({ timeout: 5_000 });
  await page.screenshot({ path: "e2e/screenshots/architecture-enforce.png", fullPage: true });
});
