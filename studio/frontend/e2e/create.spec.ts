/**
 * The create bar, driven by a real keyboard.
 *
 * **⌘/Ctrl+Enter sends, and sending is two calls in one order.** `POST /api/runs`
 * makes the draft whole — plan and sends together — and
 * `POST /api/runs/<id>/submit` is the one route that spends. There is no
 * approve step between them (decision 2026-09-04): the person pressing
 * ⌘+Enter over a prompt they can read is the yes. What only a browser can say
 * is that the Lexical editor, wired to the real bar and the real API client,
 * turns that keystroke into exactly those two writes — and that plain Enter
 * turns it into a line break and nothing else (decision 2026-09-13).
 *
 * Every `/api/**` is answered from captured fixtures (`support/api.ts`); the
 * `?fingerprint=` read between the two writes finds no twin, because the
 * captured 201's fingerprint matches nothing in the captured listing.
 */
import { expect, test } from "@playwright/test";

import {
  CREATED_RUN,
  EXPANDED,
  LIBRARY,
  PROJECT,
  fixture,
  stubApi,
} from "./support/api";
import { escaped, log, spell, wrote } from "./support/calls";
import { signIn } from "./support/session";

const LIVE = process.env.E2E_LIVE === "1";

test.beforeEach(async ({ page }) => {
  if (LIVE) return;
  await stubApi(page);
  await signIn(page, LIBRARY);
});

/** The model the bar starts on: the registry's first image entry. */
function defaultImageModel() {
  const { models } = fixture<{
    models: Record<string, { kind: string; model: string; skill: string }>;
  }>("models");
  return Object.values(models).find((entry) => entry.kind === "image")!;
}

test("⌘+Enter on the create bar makes a draft and submits it; Enter breaks the line", async ({
  page,
}) => {
  test.skip(LIVE, "it would submit a real run in the dev stack");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}`);

  const box = page.getByRole("textbox", { name: "Prompt", exact: true });
  await expect(box).toBeVisible();
  await box.click();
  await page.keyboard.type("A plain studio portrait, front on.");

  // A newline is not a send.
  await page.keyboard.press("Enter");
  await page.keyboard.type("Neutral expression.");
  await expect(box).toContainText("Neutral expression.");
  expect(wrote(calls)).toEqual([]);

  await page.keyboard.press("ControlOrMeta+Enter");

  await expect
    .poll(() => spell(wrote(calls)))
    .toEqual(["POST /api/runs", `POST /api/runs/${CREATED_RUN}/submit`]);

  const model = defaultImageModel();
  const created = wrote(calls)[0]!;
  expect(created.body).toMatchObject({
    project: PROJECT,
    kind: "image",
    // The Replicate `owner/name`, never the registry key.
    model: model.model,
    engine: model.skill,
  });
  expect((created.body.plan as { prompt: string }).prompt).toBe(
    "A plain studio portrait, front on.\nNeutral expression.",
  );

  // The bar empties once the run has gone; the kind stays.
  await expect(box).toHaveText("");
  expect(escaped(calls, page)).toEqual([]);
});

test("a tile opens the picker above the sheet, a pressed picture lands in the row, and pressed again it leaves", async ({
  page,
}) => {
  const calls = log(page);
  await page.goto(`/p/${PROJECT}`);

  // Image refs is the tile the still model offers. Pressing it is what opens
  // the picker — there is no separate control.
  await page.getByRole("group", { name: "Image refs" }).getByRole("button", { name: "Image refs" }).click();

  // The picker opens inside the project, in Media view — every picture under
  // it, newest first — with no view to switch or folder to open first.
  const picker = page.getByRole("region", { name: "Choose image refs" });
  await expect(picker).toBeVisible();
  await expect(picker.getByRole("button", { name: "Media" })).toHaveAttribute("aria-pressed", "true");
  const first = picker.getByRole("button", { name: /^Attach / }).first();
  await expect(first).toBeVisible();
  await first.click();

  // The picture is in the row now, captioned by its position, with its own way off.
  const strip = page.locator("[data-mode-strip]");
  await expect(strip.getByText("Image 1")).toBeVisible();
  await expect(strip.getByRole("button", { name: /^Remove / })).toBeVisible();

  // Marked in the picker, and the mark is a toggle: pressing it again takes
  // the picture off the row — on a phone the row's own × is under this sheet.
  const marked = picker.getByRole("button", { name: /^Remove / });
  await expect(marked).toHaveAttribute("aria-pressed", "true");
  await marked.click();
  await expect(strip.getByText("Image 1")).toHaveCount(0);
  await expect(picker.getByRole("button", { name: /^Remove / })).toHaveCount(0);

  // Attaching is not a send: nothing was written.
  expect(wrote(calls)).toEqual([]);
  expect(escaped(calls, page)).toEqual([]);
});

test("a template picked lands in the box FILLED, and there is no preview to open", async ({
  page,
}) => {
  test.skip(LIVE, "the fill would read a real bible from the dev stack");
  const calls = log(page);
  await page.goto(`/p/${PROJECT}`);

  const box = page.getByRole("textbox", { name: "Prompt", exact: true });
  await box.click();
  await page.getByRole("button", { name: "Template", exact: true }).click();
  await page.getByRole("button", { name: /Face, front/ }).first().click();

  // The template travelled; the ANSWER is what the box holds.
  await expect.poll(() => spell(wrote(calls))).toEqual([
    "POST /api/templates/expand",
  ]);
  await expect(box).toContainText(EXPANDED);
  // No citation is left to read behind an icon, which is why there is no icon.
  await expect(box).not.toContainText("{block.");
  await expect(page.getByRole("button", { name: "Preview" })).toHaveCount(0);

  expect(escaped(calls, page)).toEqual([]);
});

test("a model that works from a video offers a Source video tile, and its picker lists videos only", async ({
  page,
}) => {
  const calls = log(page);
  await page.goto(`/p/${PROJECT}`);

  // A still model has no clip. Switch to video and choose the motion model —
  // the one whose registry entry names a `clips.source`.
  const strip = page.locator("[data-mode-strip]");
  await expect(strip.getByRole("group", { name: "Source video" })).toHaveCount(0);
  await page.getByRole("group", { name: "Kind" }).getByText("Video").click();
  await page.getByRole("button", { name: /^Model: / }).click();
  await page.getByRole("option", { name: /kling-v3-motion-control/ }).click();

  // The clip tile stands beside the start frame. Pressing it opens the picker
  // on videos: the seed is stills, so Media lists the one clip and nothing else.
  await strip
    .getByRole("group", { name: "Source video" })
    .getByRole("button", { name: "Source video" })
    .click();
  const picker = page.getByRole("region", { name: "Choose a source video" });
  await expect(picker).toBeVisible();
  await picker.getByRole("button", { name: "Media" }).click();
  const offered = picker.getByRole("button", { name: /^Attach / });
  await expect(offered).toHaveCount(1);
  await expect(offered).toHaveAccessibleName(/\.mp4$/);
  await offered.click();

  // The clip is in the row, drawn as a video, captioned as what it is to the run.
  const cell = strip.getByRole("group", { name: "Source video" });
  await expect(cell.getByText("Source", { exact: true })).toBeVisible();
  await expect(cell.locator("video")).toHaveCount(1);
  expect(wrote(calls)).toEqual([]);
  expect(escaped(calls, page)).toEqual([]);
});

test("on a phone the picker is a sheet over the create sheet, and a one-picture role closes it on the pick", async ({
  page,
}) => {
  // The floating box stacked on the create sheet overran a phone's screen:
  // the title, the Folders/Media switch and the close sat above the top edge.
  await page.setViewportSize({ width: 390, height: 664 });
  await page.goto(`/p/${PROJECT}`);
  await page.getByRole("group", { name: "Kind" }).getByText("Video").click();
  const strip = page.locator("[data-mode-strip]");
  await strip.getByRole("group", { name: "Start frame" }).getByRole("button", { name: "Start frame" }).click();

  // Every control of the header is on screen, and the two views switch.
  const picker = page.getByRole("region", { name: "Choose a start frame" });
  await expect(picker).toBeVisible();
  await expect(picker.getByText("Start frame", { exact: true })).toBeInViewport();
  await expect(picker.getByRole("button", { name: "Done" })).toBeInViewport();
  await picker.getByRole("button", { name: "Folders" }).click();
  await expect(picker.getByRole("button", { name: "Folders" })).toBeInViewport();
  await picker.getByRole("button", { name: "Media" }).click();

  // A start frame is one picture: the pick closes the sheet, and the tile
  // under it is what the person sees next.
  await picker.getByRole("button", { name: /^Attach / }).first().click();
  await expect(picker).toHaveCount(0);
  // The tile, not its caption: on a phone the picture is an `ActionMenu`
  // trigger, and that draws its dropdown twin hidden beside the sheet's, so
  // the word is in the DOM twice.
  const start = strip.locator('[data-attachment="start"]');
  await expect(start).toBeVisible();
  await expect(start).toContainText("Start");
});
