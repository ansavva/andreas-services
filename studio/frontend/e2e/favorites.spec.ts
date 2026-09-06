/**
 * Favorites, end to end: press a heart in one screen, find the file in another.
 *
 * **The one thing neither unit suite can hold up.** The vitest tests mock the
 * API, so they prove the button sends the right request and the grid draws what
 * it is handed; the backend tests prove the row is written and read back. What
 * neither covers is the join — that a heart pressed in the file browser is what
 * home then shows — and that join is the whole feature.
 *
 * The stub keeps favorites in memory for the run rather than answering a
 * captured fixture, for exactly that reason: what is asserted here is that a
 * write and a later read agree. See `support/api.ts`.
 */
import { expect, test } from "@playwright/test";

import { LIBRARY, stubApi } from "./support/api";
import { signIn } from "./support/session";

const LIVE = process.env.E2E_LIVE === "1";

test.beforeEach(async ({ page }) => {
  if (LIVE) return;
  await stubApi(page);
  await signIn(page, LIBRARY);
});

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

test("home says what to press when nothing is favorited", async ({ page }) => {
  stubOnly("a live library may already hold favorites");
  await page.goto("/");

  const section = page.getByRole("region", { name: "Favorites" });
  await expect(section.getByText("Nothing favorited yet.")).toBeVisible();
  // The instruction is the whole empty state: the control that fills this
  // screen is on a different one.
  await expect(section.getByText(/Press the heart/)).toBeVisible();
});

test("a heart pressed in the browser puts the file on the home screen", async ({
  page,
}) => {
  stubOnly("the stub feed is what makes the grid deterministic");

  // The library's media view, which the reel fixture fills.
  await page.goto("/f?view=media");
  await page.waitForLoadState("networkidle");

  const heart = page.locator('main button[aria-label^="Favorite "]').first();
  await expect.poll(async () => heart.count()).toBeGreaterThan(0);
  const label = await heart.getAttribute("aria-label");

  await heart.click();
  // Optimistic, so the pressed state is the assertion rather than a reload.
  await expect(heart).toHaveAttribute("aria-pressed", "true");

  await page.goto("/");
  const section = page.getByRole("region", { name: "Favorites" });
  await expect(section.getByRole("link").first()).toBeVisible();
  // The same file, and its tile opens into the favorites feed rather than into
  // whatever folder it happens to live in.
  await expect(section.locator('a[href*="?in=fav"]').first()).toBeVisible();
  expect(label).toMatch(/^Favorite /);
});

test("pressing the heart again takes the file off", async ({ page }) => {
  stubOnly("the stub feed is what makes the grid deterministic");
  await page.goto("/f?view=media");
  await page.waitForLoadState("networkidle");

  const heart = page.locator('main button[aria-label^="Favorite "]').first();
  await heart.click();
  await expect(heart).toHaveAttribute("aria-pressed", "true");

  await heart.click();
  await expect(heart).toHaveAttribute("aria-pressed", "false");

  await page.goto("/favorites");
  await expect(page.getByText("Nothing favorited yet.")).toBeVisible();
});
