import { expect, type Page } from "@playwright/test";

// The observer's history persists across runs, so "this path is listed" proves nothing about a run
// that just happened. These helpers insist the path was seen in the last few seconds.
const route = (page: Page, text: string) =>
  page.getByRole("listitem").filter({ has: page.locator(".route", { hasText: text }) });

export async function ageOf(page: Page, text: string): Promise<number> {
  const label = await route(page, text).locator(".age").first().textContent({ timeout: 1000 }).catch(() => null);
  return label ? parseInt(label, 10) : Infinity;
}

export const expectFresh = (page: Page, text: string, seconds = 30) =>
  expect.poll(() => ageOf(page, text), { message: `${text} should have been seen in the last ${seconds}s`, timeout: 15_000 })
    .toBeLessThan(seconds);

/** Run an attack from the Attack lab, retrying when a freshly started observer had not attached yet. */
export async function runUntilSeen(page: Page, title: string, seenRoute: string, attempts = 3) {
  for (let i = 1; i <= attempts; i++) {
    await page.goto("/#attacks");
    const row = page.getByRole("listitem").filter({ hasText: title });
    await row.getByRole("button").click();
    await expect(row.getByText("Succeeded, nothing stopped it")).toBeVisible({ timeout: 40_000 });
    await page.goto("/#topology");
    if ((await expect.poll(() => ageOf(page, seenRoute), { timeout: 8_000 }).toBeLessThan(30).then(() => true, () => false))) return;
  }
  throw new Error(`${seenRoute} was never seen live after ${attempts} runs of "${title}"`);
}
