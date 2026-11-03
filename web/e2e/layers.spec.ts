import { expect, test, type Page } from "@playwright/test";

const OBSERVER = "http://localhost:8765";
const WEB = "http://localhost:8081";

const put = (page: Page, layer: string, mode: string) =>
  page.request.put(`${OBSERVER}/layers/${layer}`, { data: { mode } });
const reset = async (page: Page) => { await put(page, "mtls", "off"); await put(page, "identity", "off"); };
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
  expect(await (await page.request.get(`${OBSERVER}/layers`)).json()).toEqual({ identity: "off", mtls: "off" });
});
