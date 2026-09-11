/**
 * Favorites, end to end: file a picture on one screen, find it on another.
 *
 * **The one thing neither unit suite can hold up.** The vitest tests mock the
 * API, so they prove the button sends the right request and the grid draws what
 * it is handed; the backend tests prove the row is written and read back. What
 * neither covers is the join — that a picture favorited in the file browser is
 * what home then shows — and that join is the whole feature.
 *
 * **The gesture is a line in the tile's `⋮` now, not a heart over the
 * picture.** See `TileMenu` for why the icons over a tile went away; what these
 * cases care about is unchanged, so what moved is how they reach it.
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
  // screen is on a different one, and the sentence names where it now is.
  await expect(section.getByText(/add it to favorites/)).toBeVisible();
});

/** The first tile's `⋮`, opened. The pointer's menu; the sheet is `md:hidden`. */
async function openFirstTileMenu(page: import("@playwright/test").Page) {
  const trigger = page.locator('main button[aria-label^="Actions for "]').first();
  await expect.poll(async () => trigger.count()).toBeGreaterThan(0);
  await trigger.click();
}

test("a picture favorited in the browser lands on the home screen", async ({
  page,
}) => {
  stubOnly("the stub feed is what makes the grid deterministic");

  // The library's media view, which the reel fixture fills.
  await page.goto("/f?view=media");
  await page.waitForLoadState("networkidle");

  await openFirstTileMenu(page);
  await page.getByRole("menuitem", { name: "Add to favorites" }).click();

  // Optimistic, so what the menu says the second time it is opened is the
  // assertion rather than a reload.
  await openFirstTileMenu(page);
  await expect(page.getByRole("menuitem", { name: "Remove from favorites" })).toBeVisible();
  await page.keyboard.press("Escape");

  await page.goto("/");
  const section = page.getByRole("region", { name: "Favorites" });
  await expect(section.getByRole("link").first()).toBeVisible();
  // The same file, and its tile opens into the favorites feed rather than into
  // whatever folder it happens to live in.
  await expect(section.locator('a[href*="?in=fav"]').first()).toBeVisible();
});

test("taking it off again empties the screen", async ({ page }) => {
  stubOnly("the stub feed is what makes the grid deterministic");
  await page.goto("/f?view=media");
  await page.waitForLoadState("networkidle");

  await openFirstTileMenu(page);
  await page.getByRole("menuitem", { name: "Add to favorites" }).click();

  await openFirstTileMenu(page);
  await page.getByRole("menuitem", { name: "Remove from favorites" }).click();

  await page.goto("/favorites");
  await expect(page.getByText("Nothing favorited yet.")).toBeVisible();
});
