import { execFileSync } from "node:child_process";
import { expect, test, type Page } from "@playwright/test";

// Needs `make headlamp`. The token is read into a variable and typed into the form. It is never logged.
const HEADLAMP = "http://localhost:4466";
const kubectl = (...args: string[]) =>
  execFileSync("kubectl", ["--context", "k3d-ztp", ...args], { encoding: "utf8" }).trim();
const token = (role: "viewer" | "admin") =>
  execFileSync("../scripts/headlamp-token.sh", { encoding: "utf8", env: { ...process.env, ROLE: role } }).trim();

async function signIn(page: Page, role: "viewer" | "admin") {
  await page.goto(`${HEADLAMP}/c/main/token`);
  await page.locator("input[type=password]").fill(token(role));
  await page.getByRole("button", { name: "Authenticate" }).click();
  await expect(page).toHaveURL(`${HEADLAMP}/c/main`);
}

const podName = () => kubectl("-n", "clinic", "get", "pod", "-l", "app=web", "-o", "jsonpath={.items[0].metadata.name}");

test("a read-only token shows the clinic's pods but not its Secrets, and offers no delete", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`${HEADLAMP}/c/main/pods`);
  for (const app of ["web-", "records-api-", "records-mcp-", "agent-", "postgres-"]) {
    await expect(page.getByRole("link", { name: new RegExp(`^${app}`) }).first()).toBeVisible({ timeout: 20_000 });
  }
  await page.goto(`${HEADLAMP}/c/main/secrets`);
  await expect(page.getByText("Error: No permissions")).toBeVisible();

  await page.goto(`${HEADLAMP}/c/main/pods/clinic/${podName()}`);
  await expect(page.getByRole("heading", { name: podName() }).first()).toBeVisible();
  // Wait for the page's actions to render before claiming one is missing, or this check proves nothing.
  await expect(page.getByRole("button", { name: /logs/i }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /delete/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /terminal|edit/i })).toHaveCount(0);
  await page.screenshot({ path: "e2e/screenshots/headlamp-viewer.png" });
});

test("the same dashboard with an admin token can read Secrets and offers delete", async ({ page }) => {
  try {
    await signIn(page, "admin");
    await page.goto(`${HEADLAMP}/c/main/secrets`);
    await expect(page.getByText("db-static")).toBeVisible({ timeout: 20_000 });
    await page.goto(`${HEADLAMP}/c/main/pods/clinic/${podName()}`);
    await expect(page.getByRole("button", { name: /delete/i }).first()).toBeVisible();
    await page.screenshot({ path: "e2e/screenshots/headlamp-admin.png" });
  } finally {
    // Do not leave a standing cluster-admin identity behind.
    kubectl("delete", "clusterrolebinding", "headlamp-admin", "--ignore-not-found");
    kubectl("-n", "headlamp", "delete", "serviceaccount", "headlamp-admin", "--ignore-not-found");
  }
});
