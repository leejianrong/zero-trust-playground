import { expect, test, type Page } from "@playwright/test";

// V6 with the user layer enforced: the signed-in user's token travels web -> records-api, web -> billing -> records-api
// and web -> agent -> records-mcp -> records-api, and what each user may do follows their role.
const CLINIC = "http://localhost:8081/";
const OBSERVER = "http://localhost:8765";
const NAME = `Token Patient ${Date.now()}`;

async function setUser(page: Page, mode: string) {
  const r = await page.request.put(`${OBSERVER}/layers/user`, { data: { mode } });
  expect(r.ok()).toBe(true);
  // Services poll the ConfigMap every 2 seconds.
  // The port-forward resets idle connections, so a failed poll counts as "not yet".
  await expect.poll(async () => (await (await page.request.get("http://localhost:8081/healthz").catch(() => null))?.json())?.modes?.user, { timeout: 15_000 })
    .toBe(mode);
  // That was web's copy of the mode. records-api enforces the user layer and polls the ConfigMap on its own 2 second
  // timer, so give it a full cycle: without this the page can load before records-api has caught up and not be refused.
  await new Promise((done) => setTimeout(done, 3_000));
}

async function signIn(page: Page, user: string) {
  await page.goto(CLINIC);
  await page.getByRole("link", { name: "Sign in" }).click();
  await page.getByLabel("Username or email").fill(user);
  await page.getByLabel("Password", { exact: true }).fill(`playground-${user}`);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(new RegExp(`Signed in as ${user}`))).toBeVisible();
}

const status = (page: Page) => page.getByRole("status").first();

test.describe.configure({ mode: "serial" });
test.afterEach(async ({ page }) => { await setUser(page, "off"); });

test("without signing in, the clinic says the user layer refused it and why", async ({ page }) => {
  await setUser(page, "enforce");
  await page.goto(CLINIC);
  await expect(status(page)).toContainText("Refused by the user layer: no token");
  // The agent path refuses too, and the reason survives the hop through the agent and records-mcp.
  await page.getByRole("button", { name: "Summarise with AI" }).click();
  await expect(page.locator("#summary")).toContainText("user layer: no token");
});

test("a clinician reads, writes and summarises with the user layer enforced", async ({ page }) => {
  test.setTimeout(120_000);
  await setUser(page, "enforce");
  await signIn(page, "aisha");
  const row = page.getByRole("row", { name: /Aisha Rahman/ });
  await expect(row).toBeVisible();
  await expect(row).not.toContainText("unavailable"); // billing reached records-api with the same token

  await page.getByLabel("Name").first().fill(NAME);
  await page.getByLabel("Date of birth").first().fill("1990-01-01");
  await page.getByLabel("Diagnosis").first().fill("none");
  await page.getByRole("button", { name: "Add patient" }).click();
  await expect(status(page)).toHaveText(`Added ${NAME}.`);
  await page.getByRole("button", { name: `Delete ${NAME}` }).click();
  await expect(status(page)).toHaveText(`Deleted ${NAME}.`);

  await page.getByRole("button", { name: "Summarise with AI" }).click();
  await expect(page.locator("#summary")).toContainText("patients on file");
});

test("a receptionist reads and summarises but is refused a write, with the reason", async ({ page }) => {
  test.setTimeout(120_000);
  await setUser(page, "enforce");
  await signIn(page, "bob");
  await expect(page.getByRole("row", { name: /Aisha Rahman/ })).toBeVisible();

  await page.getByLabel("Name").first().fill(NAME);
  await page.getByLabel("Date of birth").first().fill("1990-01-01");
  await page.getByLabel("Diagnosis").first().fill("none");
  await page.getByRole("button", { name: "Add patient" }).click();
  await expect(status(page)).toContainText("Refused by the user layer: bob has receptionist");
  await expect(page.getByRole("row", { name: new RegExp(NAME) })).toHaveCount(0);

  await page.getByRole("button", { name: "Summarise with AI" }).click();
  await expect(page.locator("#summary")).toContainText("patients on file");
});
