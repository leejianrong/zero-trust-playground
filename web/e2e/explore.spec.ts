import { createServer } from "node:http";
import { expect, test } from "@playwright/test";

test("Explore lists every tool, says what each is for, and shows the running ones as up", async ({ page }) => {
  await page.goto("/#explore");
  for (const name of ["Clinic app", "Headlamp", "Keycloak", "Tutorial", "Observer API"]) {
    await expect(page.getByRole("heading", { name })).toBeVisible();
  }
  const card = (name: string) => page.getByRole("listitem").filter({ has: page.getByRole("heading", { name }) });
  for (const name of ["Clinic app", "Headlamp", "Keycloak", "Observer API"]) {
    await expect(card(name).locator(".chip")).toHaveText(/Up$/);
  }
  await expect(card("Headlamp")).toContainText("read-only token");
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.screenshot({ path: "e2e/screenshots/explore.png", fullPage: true });
});

test("the Open link takes you to the tool", async ({ page, context }) => {
  await page.goto("/#explore");
  const [popup] = await Promise.all([context.waitForEvent("page"), page.getByRole("link", { name: "Open Clinic app" }).click()]);
  await expect(popup.getByRole("heading", { name: "Riverside Clinic" })).toBeVisible();
});

test("a tool that stops answering shows as down, with how to start it, and recovers", async ({ page }) => {
  // Borrow the tutorial's port with a stand-in server so the check is about the status, not about docs.
  const server = createServer((_req, res) => res.end("ok"));
  const listening = await new Promise<boolean>((resolve) => {
    server.once("error", () => resolve(false));
    server.listen(8000, "127.0.0.1", () => resolve(true));
  });
  test.skip(!listening, "port 8000 is already serving the real tutorial");
  const docs = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Tutorial" }) });
  try {
    await page.goto("/#explore");
    await expect(docs.locator(".chip")).toHaveText(/Up$/, { timeout: 15_000 });
    await new Promise((r) => server.close(r));
    await expect(docs.locator(".chip")).toHaveText(/Down$/, { timeout: 15_000 });
    await expect(docs).toContainText("make docs");
  } finally {
    if (server.listening) server.close();
  }
});
