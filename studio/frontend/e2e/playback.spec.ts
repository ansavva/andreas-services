/**
 * The object screen, and a clip actually playing on it.
 *
 * **`/o` had no end-to-end coverage at all until this file**, for a mechanical
 * reason rather than an oversight: `support/api.ts` answered every asset with a
 * one-pixel PNG, so a `<video>` got PNG bytes, fired `error`, and the player
 * drew "this file could not be loaded". A suite can assert plenty against that
 * screen and none of it is about playback. The MP4 beside the pixel is what
 * makes the difference — see `CLIP` in `support/api.ts` for why it is generated
 * rather than captured.
 *
 * What is asserted here is what only a real browser can say: that the object
 * screen is a page in the app shell rather than the overlay it used to be, that
 * a press decodes and advances a real video in place, that closing puts the
 * poster back without navigating, and that walking the feed rewrites the
 * address instead of stacking twenty entries to escape.
 *
 * **What is deliberately absent is anything a headless desktop Chromium cannot
 * honestly answer.** Native fullscreen, iOS Safari's refusal of
 * `requestFullscreen` on a non-`<video>`, and `env(safe-area-inset-*)` are
 * device behaviour; a spec that "passed" on them here would be asserting this
 * browser's defaults and calling them a guarantee. They are on the plan's
 * phone-in-hand list and they stay there.
 */
import { expect, test, type Page } from "@playwright/test";

import {
  CHARACTER,
  CLIP_ITEM,
  LIBRARY,
  RUN_ID,
  RUN_PROJECT,
  SCENE_ID,
  STILL,
  TEXT_NODE,
  fixture,
  stubApi,
} from "./support/api";
import { signIn } from "./support/session";

const LIVE = process.env.E2E_LIVE === "1";

/**
 * Per-spec, never at module level.
 *
 * Everything in this file leans on a synthesised clip and a synthesised text
 * node, neither of which exists in a real stack — so all of it skips live. It
 * is still written one call at a time, because a module-level `test.skip` is
 * how a whole suite reports green having run nothing.
 */
function stubOnly(): void {
  test.skip(LIVE, "the clip and the text node are stub-only fixtures");
}

/** The feed `?in=recursive` walks, in the order `stubApi` serves it. */
const FEED = [
  CLIP_ITEM,
  ...fixture<{ entries: Array<{ id: string; name: string }> }>("reel").entries,
];

const at = (id: string) => `/o/${id}?in=recursive`;

test.beforeEach(async ({ page }) => {
  if (LIVE) return;
  await stubApi(page);
  await signIn(page, LIBRARY);
});

/**
 * The `<video>` the page is *about*, which is not the only one on screen.
 *
 * The filmstrip draws the clip as a tile too, and a tile is a `<video>` — so
 * `main video` matches two elements and the one that answers first is a
 * question of source order. Excluding the strip says which one is meant.
 */
async function stage(page: Page) {
  return page.evaluate(() => {
    const strip = document.querySelector('[aria-label="Neighbours"]');
    const video = [...document.querySelectorAll("main video")].find(
      (element) => !strip?.contains(element),
    ) as HTMLVideoElement | undefined;
    if (!video) return null;
    return {
      currentTime: video.currentTime,
      paused: video.paused,
      // Non-zero only once frames have really been decoded. An element that
      // fetched bytes it cannot read reports 0 here and looks fine otherwise.
      videoWidth: video.videoWidth,
      duration: video.duration,
    };
  });
}

test("the object screen is the viewer in the app shell, with the shell still around it", async ({
  page,
}) => {
  stubOnly();
  await page.goto(at(CLIP_ITEM.id));

  // The three things that keep it a page while it fills the window: the
  // shell's own navigation beside it, a crumb saying where it sits, and the
  // neighbours drawn as a strip rather than scrolled through in the dark.
  //
  // Not the filename — the object screen stopped drawing one (`ObjectFacts`),
  // and a `getByText` on it now matches the tail of the `key` line instead,
  // which is an assertion that passes without meaning what it says.
  await expect(
    page.getByRole("navigation", { name: /sections/i }).first(),
  ).toBeVisible();
  // Scoped to `main`: the sidebar carries a "Files" link of its own.
  await expect(page.locator("main").getByRole("link", { name: "Files" })).toBeVisible();
  await expect(page.getByLabel("Neighbours")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "File details" }),
  ).toBeVisible();

  // **`/o/<id>` is `ViewerFrame` now — the opened run's box — and that box is
  // `fixed`, sized from the header to the create sheet's handle.** It was an
  // ordinary page with the player capped at `65dvh` between the two, and the
  // picture was half the size the same file got when opened from a run. The
  // assertion is the box: fixed, under the header, and not under the handle.
  const frame = await page.evaluate(() => {
    const viewer = document.querySelector('[data-testid="object-viewer"]') as HTMLElement | null;
    if (!viewer) return null;
    const box = viewer.getBoundingClientRect();
    const handle = document.querySelector('button[aria-label^="Open the create panel"]');
    return {
      position: getComputedStyle(viewer).position,
      top: box.top,
      bottom: box.bottom,
      handleTop: handle?.getBoundingClientRect().top ?? null,
    };
  });
  expect(frame?.position).toBe("fixed");
  expect(frame?.top).toBe(48);
  expect(frame?.bottom).toBeLessThanOrEqual(frame?.handleTop ?? 0);
});

test("a poster plays in place, and closing returns to it without navigating", async ({
  page,
}) => {
  stubOnly();
  await page.goto(at(CLIP_ITEM.id));

  const poster = page.getByRole("button", { name: `Play ${CLIP_ITEM.name}` });
  await expect(poster).toBeVisible();

  const address = page.url();
  const entries = await page.evaluate(() => history.length);

  await poster.click();

  // Really decoding, not merely mounted: a 64px-wide frame is the fixture, and
  // an element handed bytes it cannot read would report 0 and still look like
  // this. It is also the assertion that would fail first if a Chromium ever
  // arrived without H.264 — the bundled one has it, and this says so out loud
  // rather than reporting a mysteriously stalled player.
  await expect.poll(async () => (await stage(page))?.videoWidth).toBe(64);
  await expect
    .poll(async () => (await stage(page))?.currentTime ?? 0)
    .toBeGreaterThan(0);
  await expect(
    page.getByRole("button", { name: /^(Play|Pause) \(space\)$/ }),
  ).toBeVisible();

  // **The affordance studio never had.** Close is a return to the poster, in
  // the same box, at the same address — not a way out of a mode.
  await page.getByRole("button", { name: `Close ${CLIP_ITEM.name}` }).click();
  await expect(poster).toBeVisible();
  expect(page.url()).toBe(address);
  expect(await page.evaluate(() => history.length)).toBe(entries);
});

test("space and m reach the player from the page", async ({ page }) => {
  stubOnly();
  // The keys `useKeyboardNav` names only work because `MediaPlayer` hands its
  // controls up — a wiring that a unit test can only assert one half of.
  await page.goto(at(CLIP_ITEM.id));
  // The player hands its controls up on mount, so the keys are dead until the
  // poster is on screen — waiting for it is waiting for that.
  await expect(
    page.getByRole("button", { name: `Play ${CLIP_ITEM.name}` }),
  ).toBeVisible();

  await page.keyboard.press(" ");
  await expect.poll(async () => (await stage(page))?.paused).toBe(false);

  await page.keyboard.press("m");
  await expect(page.getByRole("button", { name: "Mute (m)" })).toBeVisible();

  await page.keyboard.press(" ");
  await expect.poll(async () => (await stage(page))?.paused).toBe(true);
});

test("prev and next walk the feed and rewrite the address rather than pushing", async ({
  page,
}) => {
  stubOnly();
  await page.goto(at(FEED[0]!.id));
  const entries = await page.evaluate(() => history.length);

  await page.getByRole("button", { name: "Next (→)" }).click();
  await expect(page).toHaveURL(at(FEED[1]!.id));

  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(at(FEED[2]!.id));

  await page.keyboard.press("ArrowLeft");
  await expect(page).toHaveURL(at(FEED[1]!.id));

  // Three steps, no new entries. Twenty files walked past would otherwise be
  // twenty back-presses to escape.
  expect(await page.evaluate(() => history.length)).toBe(entries);
});

test("stepping stops at both ends of the feed", async ({ page }) => {
  stubOnly();
  const last = FEED[FEED.length - 1]!;

  await page.goto(at(FEED[0]!.id));
  await expect(
    page.getByRole("button", { name: "Previous (←)" }),
  ).toBeDisabled();
  await page.keyboard.press("ArrowLeft");
  // Long enough for a rewrite to have happened if one were coming: the address
  // is rewritten from an effect, in the tick after the keystroke.
  await page.waitForTimeout(250);
  await expect(page).toHaveURL(at(FEED[0]!.id));

  await page.goto(at(last.id));
  await expect(page.getByRole("button", { name: "Next (→)" })).toBeDisabled();
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(250);
  await expect(page).toHaveURL(at(last.id));
});

test("a cold link with no context shows the file and says what it belongs to", async ({
  page,
}) => {
  stubOnly();
  // The share link's durable half: the id alone, with the `?in=` a browser
  // would have added stripped off.
  await page.goto(`/o/${STILL.id}`);

  // The picture itself, not its name: see the note in the app-shell test above
  // for why a `getByText` on the filename no longer proves anything.
  await expect(page.locator("main img").first()).toBeVisible();

  // One pane is not a sequence, so there is no strip — and the way back is the
  // owner walk instead of a neighbour.
  await expect(page.getByLabel("Neighbours")).toHaveCount(0);

  const owner = page.getByRole("button", { name: `in ${STILL.owner!.name}` });
  await expect(owner).toBeVisible();
  await owner.click();
  await expect(page).toHaveURL(`/c/${CHARACTER}`);
});

test("a non-media node still opens the text page", async ({ page }) => {
  stubOnly();
  // `/o/<id>` has always been the address of a `prompt.json` as well as of a
  // frame, and Phase C moved the branch that decides which.
  await page.goto(`/o/${TEXT_NODE.id}`);

  // No `dialog` role any more — `TextPage` is an ordinary page inside
  // `AppLayout` now, with its own `PageBar` heading rather than a takeover.
  await expect(
    page.getByRole("heading", { name: TEXT_NODE.name }),
  ).toBeVisible();
  await expect(page.getByText('"shot"')).toBeVisible();
  await expect(page.getByRole("button", { name: "Close (Esc)" })).toBeVisible();
});

test("playing a clip sends no request off the origin", async ({ page }) => {
  stubOnly();
  // `browse.spec.ts` asserts this for the listings. Playback is the case that
  // would break it: a presigned URL that reached a fixture unscrubbed is
  // fetched by the media element itself, not by the app's own code.
  const escaped: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith("http://localhost:4173") && !url.startsWith("data:"))
      escaped.push(url);
  });

  await page.goto(at(CLIP_ITEM.id));
  await page.getByRole("button", { name: `Play ${CLIP_ITEM.name}` }).click();
  await expect
    .poll(async () => (await stage(page))?.currentTime ?? 0)
    .toBeGreaterThan(0);
  await page.waitForLoadState("networkidle");

  expect(escaped).toEqual([]);
});

/**
 * **The page must never scroll sideways**, and this is a regression guard for a
 * bug that shipped invisibly to every other check.
 *
 * The filmstrip is `overflow-x-auto`, so its 71 tiles are its own business. But
 * each tile's `sr-only` label is `position: absolute`, and the tile itself was
 * not positioned — so those labels resolved their containing block ABOVE the
 * scroller, escaped its clip, and handed their static positions to the ROOT
 * scroller. `document.documentElement.scrollWidth` measured 4984 against a 390
 * viewport while `document.body.scrollWidth` stayed a well-behaved 390, and the
 * page scrolled 4.6k pixels into empty dark.
 *
 * Two traps for anyone re-testing this by hand:
 *  - It only appears once layout settles. At 500ms after `goto` the document
 *    measures clean; the overflow arrives with the thumbnails.
 *  - `body.scrollWidth` never notices. The overflow is on the root element.
 */
for (const [label, width] of [
  ["desktop", 1280],
  ["mobile", 390],
] as const) {
  test(`the page does not scroll horizontally at ${label}`, async ({
    page,
  }) => {
    stubOnly();
    await page.setViewportSize({ width, height: 844 });
    await page.goto(at(CLIP_ITEM.id));
    await page.waitForLoadState("networkidle");

    await expect
      .poll(async () =>
        page.evaluate(() => {
          const root = document.documentElement;
          return root.scrollWidth - root.clientWidth;
        }),
      )
      .toBe(0);

    // The property above is the diagnosis; this is the symptom a person meets.
    const scrolled = await page.evaluate(() => {
      window.scrollTo(2000, 0);
      const x = window.scrollX;
      window.scrollTo(0, 0);
      return x;
    });
    expect(scrolled).toBe(0);
  });
}

/**
 * **Opening the object screen must not scroll the page**, and the filmstrip
 * must still centre the tile it is on.
 *
 * These are one test because they are one trade. The strip used to call
 * `tile.scrollIntoView({ block: "nearest", inline: "center" })`, and
 * `block: "nearest"` does not mean "do not scroll vertically" — when the strip
 * sits below the fold, as it does at 390px, the browser scrolls every
 * scrollable ancestor to reveal it. `window.scrollY` settled at 85 and the top
 * of the content column went under the sticky header. Scrolling the strip by
 * hand fixes that, and the second half of this test is what stops the fix from
 * being "never scroll at all".
 *
 * **What is asserted on top is Close, not the filename.** The name was the
 * page's `<h2>` when this was written and is not drawn at all now — see
 * `ObjectFacts`. Close is the better subject anyway: it sits in the same first
 * row, and a control you cannot press is a worse outcome than a word you
 * cannot read.
 */
test("opening an object does not scroll the page, and the strip still centres", async ({
  page,
}) => {
  stubOnly();
  await page.setViewportSize({ width: 390, height: 844 });

  // Deep in the feed, so centring has somewhere to scroll to.
  const target = FEED[8]!;
  await page.goto(at(target.id));
  await page.waitForLoadState("networkidle");

  await expect.poll(async () => page.evaluate(() => window.scrollY)).toBe(0);

  // Genuinely on top at its own centre, not merely present in the DOM.
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const close = document.querySelector('button[aria-label="Close (Esc)"]');
        if (!close) return "missing";
        const box = close.getBoundingClientRect();
        const hit = document.elementFromPoint(
          Math.round(box.x + box.width / 2),
          Math.round(box.y + box.height / 2),
        );
        return hit === close || close.contains(hit) ? "on top" : "covered";
      }),
    )
    .toBe("on top");

  // And the strip did its own job: a tile nine in is not left at rest.
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const strip = document.querySelector('[aria-label="Neighbours"]');
        return strip ? strip.scrollLeft : 0;
      }),
    )
    .toBeGreaterThan(0);
});

/**
 * **The current tile's ring must not be clipped by its own scroller.**
 *
 * The filmstrip marks the current tile with `outline` + `outline-offset-2`, and
 * an outline paints OUTSIDE the element's box. The strip had vertical padding
 * and none horizontal, so `overflow-x-auto` sliced the ring off the first and
 * last tiles — the two most often current, since a feed usually opens on its
 * first item. Reported from a real screenshot, not caught by any assertion.
 */
test("the current tile's selection ring is not clipped", async ({ page }) => {
  stubOnly();
  await page.goto(at(CLIP_ITEM.id));
  await page.waitForLoadState("networkidle");

  // 2px offset + 2px stroke is the ring; anything less than 4 clips it.
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const strip = document.querySelector('[aria-label="Neighbours"]');
        const tile = strip?.querySelector('[aria-current="true"]');
        if (!strip || !tile) return -1;
        return Math.round(
          tile.getBoundingClientRect().left -
            strip.getBoundingClientRect().left,
        );
      }),
    )
    .toBeGreaterThanOrEqual(4);
});

/**
 * **The opened run is a lightbox: the stage and the rail side by side, and
 * the rail under the stage on a phone.**
 *
 * Two assertions in one test because they are one decision. Above `md` the
 * run's own details sit in a rail beside the picture, the way the mockup
 * draws it. Below it there is one column and the OUTPUT LEADS — the thing a
 * person opened the run for is first, and the rail scrolls under it.
 *
 * The output is a video and must render as one — an `.mp4` handed to <img>
 * is the broken thumbnail this suite exists to keep fixed.
 */
for (const [label, width, splits] of [
  ["desktop", 1440, true],
  ["mobile", 390, false],
] as const) {
  test(`the opened run ${splits ? "puts the rail beside the stage" : "stacks the rail under the stage"} at ${label}`, async ({
    page,
  }) => {
    stubOnly();
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/p/${RUN_PROJECT}/r/${RUN_ID}`);
    await page.waitForLoadState("networkidle");

    const dialog = page.getByRole("dialog", { name: "Run" });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("video").first()).toBeVisible();
    await expect(dialog.getByRole("complementary", { name: "Run details" })).toBeVisible();

    const geometry = await page.evaluate(() => {
      const dialog = document.querySelector('[role="dialog"][aria-label="Run"]');
      const video = dialog?.querySelector("video");
      const rail = dialog?.querySelector('aside[aria-label="Run details"]');
      if (!video || !rail) return null;
      const v = video.getBoundingClientRect();
      const r = rail.getBoundingClientRect();
      return {
        sideBySide: r.left >= v.right - 1,
        railBelow: r.top >= v.bottom - 1,
      };
    });

    expect(geometry).not.toBeNull();
    expect(geometry!.sideBySide).toBe(splits);
    if (!splits) expect(geometry!.railBelow).toBe(true);
  });
}

/**
 * **The scene screen's split is INSIDE a shot, and the cut is above it.**
 *
 * This asserted a page-level split and was wrong about the page: a run has one
 * payload and one output, so its screen splits once; a scene has a RESULT and
 * then N shots that each have inputs and outputs of their own. So the cut leads
 * at full width — it is the scene, not a column beside it — and the two-column
 * treatment belongs to each shot.
 *
 * A shot's outputs are plural on purpose: a re-render keeps the take it
 * replaced, and comparing them is the reason to re-render at all.
 */
for (const [label, width, splits] of [
  ["desktop", 1440, true],
  ["mobile", 390, false],
] as const) {
  test(`a scene's shot ${splits ? "splits" : "stacks output-first"} at ${label}`, async ({
    page,
  }) => {
    stubOnly();
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/s/${SCENE_ID}`);
    await page.waitForLoadState("networkidle");

    const geometry = await page.evaluate(() => {
      const cut = [...document.querySelectorAll("section")].find((s) =>
        /^(Cuts|The cut)/.test(s.textContent ?? ""),
      );
      const shot = document.querySelector("article");
      const inputs = shot?.querySelector('[class*="lg:col-start-1"]');
      const outputs = shot?.querySelector('[class*="lg:col-start-2"]');
      if (!cut || !shot || !inputs || !outputs) return null;
      const c = cut.getBoundingClientRect();
      const i = inputs.getBoundingClientRect();
      const o = outputs.getBoundingClientRect();
      const board = shot.getBoundingClientRect();
      return {
        // The cut is above every shot, and spans the same width the storyboard
        // does rather than half of it. Measured against the board rather than
        // `main`, whose own padding makes it wider than any of its children.
        cutAboveShots: c.bottom <= board.top + 1,
        cutIsFullWidth: c.width >= board.width - 2,
        shotSplits: o.left >= i.right - 1,
        outputAbove: o.top < i.top,
      };
    });

    expect(geometry).not.toBeNull();
    expect(geometry!.cutAboveShots).toBe(true);
    expect(geometry!.cutIsFullWidth).toBe(true);
    expect(geometry!.shotSplits).toBe(splits);
    if (!splits) expect(geometry!.outputAbove).toBe(true);
  });
}

test("a shot's runs are a tab, not a list under its inputs", async ({
  page,
}) => {
  stubOnly();
  await page.goto(`/s/${SCENE_ID}`);
  await page.waitForLoadState("networkidle");

  const runs = page.getByRole("tab", { name: /^Runs/ });
  await expect(runs).toBeVisible();
  await runs.click();
  await expect(page.getByText("clip", { exact: true }).first()).toBeVisible();
});
