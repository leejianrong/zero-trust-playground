import { expect, test } from "@playwright/test";
import { expectFresh, runUntilSeen } from "./fresh";

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
  await expect(rows).toHaveCount(5);
  for (const title of ["Read patient records straight from Postgres", "Call records-api with no identity", "Reach billing from another namespace", "Call the MCP server with no identity", "Let an agent summarise a poisoned record"]) {
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

test("the injection attack leaves the clinic unchanged and the agent's path is seen live", async ({ page }) => {
  await runUntilSeen(page, "Let an agent summarise a poisoned record", "agent → records-mcp");
  for (const route of ["attacker → agent", "agent → records-mcp", "records-mcp → records-api"]) {
    await expectFresh(page, route);
  }
  // The attack plants its own records and removes them, so the clinic is as it was.
  const list = await (await page.request.get("http://localhost:8081/api/patients")).json();
  expect(list.map((p: { name: string }) => p.name)).not.toContain("Poisoned Note");
  expect(list.map((p: { name: string }) => p.name)).not.toContain("Decoy Target");
});
