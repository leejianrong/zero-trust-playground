import { expect, test } from "@playwright/test";
import { expectFresh, runUntilSeen } from "./fresh";

// Captures the images the tutorial uses. It makes fresh activity first, so every path on the
// Topology is current (older ones fade) and the agent's path is present.
const ASSETS = "../docs/tutorial/assets";

test("capture the Topology and Attack lab for the tutorial", async ({ page }) => {
  test.setTimeout(120_000);
  await page.emulateMedia({ colorScheme: "light" });
  await page.setViewportSize({ width: 1280, height: 900 });

  // Run every attack, insisting each one is seen live, so every line on the picture is current.
  const attacks: [string, string][] = [
    ["Read patient records straight from Postgres", "attacker → postgres"],
    ["Call records-api with no identity", "attacker → records-api"],
    ["Reach billing from another namespace", "attacker → billing"],
    ["Call the MCP server with no identity", "attacker → records-mcp"],
    ["Let an agent summarise a poisoned record", "agent → records-mcp"],
  ];
  for (const [title, seen] of attacks) await runUntilSeen(page, title, seen);

  await page.goto("/#attacks");
  await page.screenshot({ path: `${ASSETS}/attacks-light.png`, fullPage: true });

  await page.goto("/#topology");
  await page.getByRole("button", { name: "Use the app" }).click();
  for (const route of ["user → web", "attacker → agent", "agent → records-mcp", "records-mcp → records-api"]) {
    await expectFresh(page, route, 60);
  }
  await page.waitForTimeout(1500); // let the lines settle
  await page.screenshot({ path: `${ASSETS}/topology-light.png`, fullPage: true });
});
