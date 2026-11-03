import { expect, test } from "@playwright/test";

// With no layers on, the clinic app is wide open. Needs `make clinic` as well as `make echo`.

test("Use the app draws the path a visit takes through the services", async ({ page }) => {
  await page.goto("/#topology");
  await page.getByRole("button", { name: "Use the app" }).click();
  const paths = page.getByRole("list").filter({ hasText: "records-api → postgres" });
  for (const route of ["user → web", "web → records-api", "web → billing", "billing → records-api", "records-api → postgres"]) {
    await expect(paths.getByText(route, { exact: true })).toBeVisible({ timeout: 20_000 });
  }
});

test("every baseline attack succeeds, and an attack on Postgres shows up as an edge", async ({ page }) => {
  await page.goto("/#attacks");
  const rows = page.getByRole("listitem").filter({ hasText: "Run attack" });
  await expect(rows).toHaveCount(3);
  for (const title of ["Read patient records straight from Postgres", "Call records-api with no identity", "Reach billing from another namespace"]) {
    const row = rows.filter({ hasText: title });
    await row.getByRole("button").click();
    await expect(row.getByText("Succeeded, nothing stopped it")).toBeVisible({ timeout: 30_000 });
    await expect(row.getByText("As expected")).toBeVisible();
  }
  await page.goto("/#topology");
  await expect(page.getByText("attacker → postgres", { exact: true })).toBeVisible();
  await expect(page.getByText("attacker → billing", { exact: true })).toBeVisible();
  await expect(page.getByText("allowed, nothing stopped it").first()).toBeVisible();
});

for (const theme of ["light", "dark"] as const) {
  test(`screenshots of topology and attack lab, ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/#topology");
    await page.getByRole("button", { name: "Use the app" }).click();
    await expect(page.getByText("records-api → postgres", { exact: true })).toBeVisible({ timeout: 20_000 });
    await page.screenshot({ path: `e2e/screenshots/topology-${theme}.png`, fullPage: true });
    await page.goto("/#attacks");
    await page.screenshot({ path: `e2e/screenshots/attacks-${theme}.png`, fullPage: true });
  });
}
