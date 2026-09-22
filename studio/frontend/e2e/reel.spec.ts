/**
 * The project reel: opened from the bar, oldest first, hearted with a double
 * tap, and picked up where it was left.
 *
 * **What only a browser can hold up here is the scroll.** The unit suite
 * pins which item is current from the walk's answer; what it cannot do is
 * scroll a snapping column, because jsdom lays nothing out. So these cases
 * move the real scroller and read the position the observer reports — and
 * then leave, come back, and read it again, which is the whole of "remember
 * where I left off".
 *
 * The stub answers every `depth=all` walk with the captured reel behind one
 * clip, whatever the sort — so the ORDER is asserted on the request the app
 * made, not on what came back.
 */
import { expect, test, type Page } from "@playwright/test";

import { CLIP_ITEM, LIBRARY, PROJECT, stubApi } from "./support/api";
import { log, wrote } from "./support/calls";
import { signIn } from "./support/session";

const LIVE = process.env.E2E_LIVE === "1";

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

test.beforeEach(async ({ page }) => {
  if (LIVE) return;
  await stubApi(page);
  await signIn(page, LIBRARY);
});

const reel = (page: Page) => page.getByRole("dialog", { name: /reel$/ });
/** The chrome's place: `n of N`, with a trailing `…` while the walk is still paging. */
const position = (page: Page) => reel(page).getByText(/^\d+ of \d+/);

/** One pane down, through the real scroller — a swipe, as the browser sees it. */
async function swipeUp(page: Page, panes = 1) {
  await page.evaluate((count) => {
    const scroller = document.querySelector<HTMLElement>(".reel-scroller")!;
    scroller.scrollBy({ top: scroller.clientHeight * count, behavior: "auto" });
  }, panes);
}

async function toEnd(page: Page) {
  await page.evaluate(() => {
    const scroller = document.querySelector<HTMLElement>(".reel-scroller")!;
    scroller.scrollTo({ top: scroller.scrollHeight, behavior: "auto" });
  });
}

test("Play reel opens the project's reel, oldest first", async ({ page }) => {
  stubOnly("the stub walk is what makes the count deterministic");
  const calls = log(page);

  await page.goto(`/p/${PROJECT}`);
  await page.getByRole("button", { name: "Play reel" }).click();

  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}/reel$`));
  await expect(reel(page)).toBeVisible();
  await expect(position(page)).toHaveText(/^1 of \d+$/);

  // The walk is the project's root, recursive, images and videos, OLDEST
  // first — the one listing in the app that runs that way.
  const walk = calls.find(
    (call) => call.path === "/api/nodes" && call.query.get("depth") === "all",
  );
  expect(walk?.query.get("sort")).toBe("oldest");
  expect(walk?.query.get("kind")).toBe("image,video");
});

test("a double tap hearts the item on screen", async ({ page }) => {
  stubOnly("favorites are stub state");
  const calls = log(page);

  await page.goto(`/p/${PROJECT}/reel`);
  await expect(position(page)).toHaveText(/^1 of/);

  await reel(page).getByTestId("reel-pane").first().dblclick();

  await expect(reel(page).getByTestId("reel-favorited")).toBeVisible();
  // The first item is the clip the stub leads its walk with.
  await expect
    .poll(() => wrote(calls).map((call) => `${call.method} ${call.path}`))
    .toContain(`POST /api/favorites/${CLIP_ITEM.id}`);
});

test("it remembers where it was left, and starts over from the end", async ({ page }) => {
  stubOnly("the stub walk is what makes the count deterministic");

  await page.goto(`/p/${PROJECT}/reel`);
  await expect(position(page)).toHaveText(/^1 of/);

  await swipeUp(page);
  await expect(position(page)).toHaveText(/^2 of/);

  // Leave by the key, and come back by the bar.
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}$`));
  await page.getByRole("button", { name: "Play reel" }).click();
  await expect(position(page)).toHaveText(/^2 of/);

  // The end: the place is let go of, and the way back is offered.
  await toEnd(page);
  await expect(position(page)).toHaveText(/^(\d+) of \1$/);
  await expect(reel(page).getByRole("button", { name: "Start over" })).toBeVisible();

  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Play reel" }).click();
  await expect(position(page)).toHaveText(/^1 of/);
});
