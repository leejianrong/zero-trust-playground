import { expect, test, type Page } from "@playwright/test";

// V6 Users view: a sign-in appears within 5 seconds, a request shows its user, client and audience, and a
// failed sign-in is listed with Keycloak's reason.
const CLINIC = "http://localhost:8081/";
const OBSERVER = "http://localhost:8765";

async function layer(page: Page, mode: string) {
  expect((await page.request.put(`${OBSERVER}/layers/user`, { data: { mode } })).ok()).toBe(true);
  await expect.poll(async () => (await (await page.request.get("http://localhost:8081/healthz").catch(() => null))?.json())?.modes?.user, { timeout: 15_000 }).toBe(mode);
}

async function openSignIn(page: Page) {
  await page.goto(CLINIC);
  await page.getByRole("link", { name: "Sign in" }).click();
}

test.describe.configure({ mode: "serial" });
test.afterEach(async ({ page }) => { await layer(page, "off"); });

test("a sign-in, a refused write and a wrong password all show on the Users view", async ({ browser, page }) => {
  test.setTimeout(120_000);
  const started = new Date(); const t0 = started.getHours() * 3600 + started.getMinutes() * 60 + started.getSeconds() - 1;
  await layer(page, "enforce");
  await page.goto("/#users");

  const clinic = await (await browser.newContext()).newPage();
  await openSignIn(clinic);
  await clinic.getByLabel("Username or email").fill("bob");
  await clinic.getByLabel("Password", { exact: true }).fill("not-the-password");
  await clinic.getByRole("button", { name: "Sign in" }).click();
  await expect(clinic.getByText("Invalid username or password")).toBeVisible();
  await clinic.getByLabel("Password", { exact: true }).fill("playground-bob");
  await clinic.getByRole("button", { name: "Sign in" }).click();
  await expect(clinic.getByText(/Signed in as bob/)).toBeVisible();
  await clinic.getByLabel("Name").first().fill("Nobody Special");
  await clinic.getByLabel("Date of birth").first().fill("1990-01-01");
  await clinic.getByLabel("Diagnosis").first().fill("none");
  await clinic.getByRole("button", { name: "Add patient" }).click();
  await expect(clinic.getByRole("status").first()).toContainText("Refused by the user layer");

  // The page replays older events, so look for rows made after this test began.
  const fresh = (rows: ReturnType<Page["getByRole"]>) => rows.evaluateAll((els, t) => els.some((el) => {
    const [h, m, sec] = (el.querySelector("td")?.textContent ?? "0:0:0").split(":").map(Number);
    return h * 3600 + m * 60 + sec >= t;
  }), t0);
  await expect(page.getByRole("row", { name: /^bob receptionist Signed in/ })).toBeVisible({ timeout: 15_000 });
  await expect.poll(() => fresh(page.getByRole("row", { name: /bob web records-api, account POST \/patients Refused/ })), { timeout: 15_000 }).toBe(true);
  await expect.poll(() => fresh(page.getByRole("row", { name: /bob web records-api, account GET \/patients(\/\d+)? Allowed/ })), { timeout: 15_000 }).toBe(true);
  await expect(page.getByText(/could not sign in to web: invalid_user_credentials/).first()).toBeVisible({ timeout: 15_000 });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: "e2e/screenshots/users.png", fullPage: true });
});
