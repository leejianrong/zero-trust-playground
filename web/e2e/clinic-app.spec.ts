import { expect, test } from "@playwright/test";

const CLINIC = "http://localhost:8081/";
const NAME = `E2E Patient ${Date.now()}`;

test("add, edit and delete a patient through the clinic page", async ({ page }) => {
  await page.goto(CLINIC);
  await expect(page.getByRole("heading", { name: "Riverside Clinic" })).toBeVisible();
  await expect(page.getByRole("row", { name: /Aisha Rahman/ })).toBeVisible();

  // Create
  await page.getByLabel("Name").first().fill(NAME);
  await page.getByLabel("Date of birth").first().fill("1993-04-21");
  await page.getByLabel("Diagnosis").first().fill("Seasonal allergies");
  await page.getByRole("button", { name: "Add patient" }).click();
  await expect(page.getByRole("status").first()).toHaveText(`Added ${NAME}.`);
  const row = page.getByRole("row", { name: new RegExp(NAME) });
  await expect(row).toContainText("1993-04-21");
  await expect(row).toContainText("none"); // billing has no invoice for a new patient

  // Update
  await page.getByRole("button", { name: `Edit ${NAME}` }).click();
  await page.getByRole("dialog").getByLabel("Diagnosis").fill("Hay fever");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").first()).toHaveText(`Saved ${NAME}.`);
  await expect(row).toContainText("Hay fever");

  // It is really in the database, not just on the page
  await page.reload();
  await expect(row).toContainText("Hay fever");

  // Delete
  await page.getByRole("button", { name: `Delete ${NAME}` }).click();
  await expect(page.getByRole("status").first()).toHaveText(`Deleted ${NAME}.`);
  await expect(row).toHaveCount(0);
  await page.reload();
  await expect(row).toHaveCount(0);
});

test("a bad entry is refused with a reason, and nothing is saved", async ({ page }) => {
  await page.goto(CLINIC);
  await expect(page.getByRole("row", { name: /Aisha Rahman/ })).toBeVisible(); // rows load asynchronously
  const before = await page.getByRole("row").count();
  // The browser caps the name at 100 characters. Lift that cap to prove the server enforces it too.
  await page.evaluate(() => document.querySelector("input[name=name]")!.removeAttribute("maxlength"));
  await page.getByLabel("Name").first().fill("x".repeat(101));
  await page.getByLabel("Date of birth").first().fill("2000-01-01");
  await page.getByRole("button", { name: "Add patient" }).click();
  await expect(page.getByRole("status").first()).toContainText(/at most 100 characters/);
  expect(await page.getByRole("row").count()).toBe(before);
});

test("one click in the clinic page is traceable across services on the dashboard", async ({ page, request }) => {
  const name = `Traced ${Date.now()}`;
  await page.goto(CLINIC);
  try {
  await page.getByLabel("Name").first().fill(name);
  await page.getByLabel("Date of birth").first().fill("1980-02-02");
  await page.getByRole("button", { name: "Add patient" }).click();
  await expect(page.getByRole("status").first()).toHaveText(`Added ${name}.`);
  // The page shows the trace id of its last request. Find exactly that request in the observer's events.
  await expect(page.locator("#trace")).toHaveText(/^[0-9a-f]{12}$/);
  const trace = (await page.locator("#trace").textContent())!;
  await expect(async () => {
    const body = await (await request.get(`http://localhost:8765/events?follow=false&trace=${trace}`)).text();
    const hops = body.split("\n").filter((l) => l.startsWith("data:")).map((l) => JSON.parse(l.slice(6)))
      .map((e) => `${e.src} → ${e.dst}`);
    expect(hops).toEqual(expect.arrayContaining(["user → web", "web → records-api"]));
  }).toPass({ timeout: 20_000 });

  } finally {
    // Leave the database as we found it, even when an assertion above failed.
    await page.reload();
    await expect(page.getByRole("row", { name: /Aisha Rahman/ })).toBeVisible();
    const del = page.getByRole("button", { name: `Delete ${name}` });
    if (await del.count()) await del.click();
    await expect(page.getByRole("row", { name: new RegExp(name) })).toHaveCount(0);
  }
});
