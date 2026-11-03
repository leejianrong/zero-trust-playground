import { execFileSync } from "node:child_process";
import { expect, type Locator, test } from "@playwright/test";

const WORKLOADS = ["echo-a", "echo-b"];
const valid = (card: Locator) => card.getByRole("img", { name: "Identity valid" });

test("Identity view shows both workloads with a live countdown", async ({ page }) => {
  await page.goto("/#identity");
  for (const sa of WORKLOADS) {
    await expect(page.locator("article", { hasText: sa })).toBeVisible({ timeout: 30_000 });
  }
  await expect(page.getByText("Not live")).toHaveCount(0);
  const card = page.locator("article", { hasText: "echo-a" });
  await expect(valid(card)).toBeVisible();
  const first = await card.getByRole("figure").getAttribute("aria-label");
  await page.waitForTimeout(3000);
  expect(await card.getByRole("figure").getAttribute("aria-label")).not.toBe(first);
});

test("a rotation shows a new current serial at the top of the history", async ({ page }) => {
  await page.goto("/#identity");
  const card = page.locator("article", { hasText: "echo-a" });
  await card.getByRole("button", { name: /echo-a/ }).click(); // the history lives in the card's dialog
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
    await expect(valid(page.locator("article", { hasText: WORKLOADS[0] }))).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `e2e/screenshots/identity-${theme}.png`, fullPage: true });
  });
}

test("removing the registration leaves the identity to expire", async ({ page }) => {
  test.setTimeout(300_000);
  const kubectl = (...args: string[]) => execFileSync("kubectl", ["--context", "k3d-ztp", ...args], { cwd: ".." });
  await page.goto("/#identity");
  const card = page.locator("article", { hasText: "echo-b" });
  await expect(valid(card)).toBeVisible({ timeout: 30_000 });
  try {
    kubectl("delete", "clusterspiffeid", "clinic");
    await expect(card.getByRole("img", { name: "Registration removed" })).toBeVisible({ timeout: 30_000 });
    // 2 minute TTL: with no registration the workload cannot renew, so the ring runs out.
    await expect(card.getByRole("figure")).toHaveAttribute("aria-label", "expired", { timeout: 180_000 });
    await page.screenshot({ path: "e2e/screenshots/identity-stale.png" });
  } finally {
    kubectl("apply", "-f", "deploy/spire/clusterspiffeid-clinic.yaml");
  }
  await expect(valid(card)).toBeVisible({ timeout: 120_000 });
});

test("the page says so when the event stream is down, and only then", async ({ page }) => {
  await page.route("**/events", (route) => route.abort());
  await page.goto("/#identity");
  await expect(page.getByText("Not live: the observer is not reachable")).toBeVisible({ timeout: 15_000 });
});

test("the theme icons switch the theme", async ({ page }) => {
  await page.goto("/#identity");
  await page.getByRole("button", { name: "Dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "System theme" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
});

test("clicking a card opens a dialog with its SPIFFE ID and history, and Escape closes it", async ({ page }) => {
  await page.goto("/#identity");
  const card = page.locator("article", { hasText: "echo-a" });
  await expect(card.getByRole("dialog")).toBeHidden();
  await card.getByRole("button", { name: /echo-a/ }).click();
  const dialog = page.getByRole("dialog", { name: "echo-a identity" });
  await expect(dialog.getByLabel("SPIFFE ID spiffe://playground.local/ns/clinic/sa/echo-a")).toBeVisible();
  await expect(dialog.getByText("Rotation history")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/identity-dialog.png" });
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
