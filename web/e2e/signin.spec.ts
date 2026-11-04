import { expect, test, type Page } from "@playwright/test";

// V6 sign in: the clinic page sends the browser to Keycloak (authorization code with PKCE), shows who signed in
// and their role, and sign out ends the session. The user layer stays off, so the page works without signing in.
const CLINIC = "http://localhost:8081/";

async function signIn(page: Page, user: string) {
  await page.goto(CLINIC);
  await page.getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/localhost:8180\/realms\/clinic/);
  await page.getByLabel("Username or email").fill(user);
  await page.getByLabel("Password", { exact: true }).fill(`playground-${user}`);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(CLINIC);
}

test("the page works without signing in", async ({ page }) => {
  await page.goto(CLINIC);
  await expect(page.getByRole("row", { name: /Aisha Rahman/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
});

for (const [user, role] of [["aisha", "clinician"], ["bob", "receptionist"]]) {
  test(`${user} signs in, sees their role, and signing out ends the session`, async ({ page }) => {
    await signIn(page, user);
    await expect(page.getByText(`Signed in as ${user} (${role})`)).toBeVisible();
    await page.reload();
    await expect(page.getByText(`Signed in as ${user} (${role})`)).toBeVisible();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
    // Keycloak's own session ended too, so signing in again asks for the password.
    await page.getByRole("link", { name: "Sign in" }).click();
    await expect(page.getByLabel("Username or email")).toBeVisible();
  });
}
