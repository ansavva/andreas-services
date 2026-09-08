/**
 * The create bar, driven by a real keyboard.
 *
 * **Enter sends, and sending is two calls in one order.** `POST /api/runs`
 * makes the draft whole — plan and sends together — and
 * `POST /api/runs/<id>/submit` is the one route that spends. There is no
 * approve step between them (decision 2026-09-04): the person pressing Enter
 * over a prompt they can read is the yes. What only a browser can say is that
 * the Lexical editor, wired to the real bar and the real API client, turns
 * that keystroke into exactly those two writes — and that Shift+Enter turns
 * it into a line break and nothing else.
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

test("Enter on the create bar makes a draft and submits it; Shift+Enter breaks the line", async ({
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
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.type("Neutral expression.");
  await expect(box).toContainText("Neutral expression.");
  expect(wrote(calls)).toEqual([]);

  await page.keyboard.press("Enter");

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

test("a tile opens the picker above the sheet, and a pressed picture lands in the row", async ({
  page,
}) => {
  const calls = log(page);
  await page.goto(`/p/${PROJECT}`);

  // Image refs is the tile the still model offers. Pressing it is what opens
  // the picker — there is no separate control.
  await page.getByRole("group", { name: "Image refs" }).getByRole("button", { name: "Image refs" }).click();

  // The picker is the library's own navigation: it opens on the project's
  // folder, and Media is every picture under it.
  const picker = page.getByRole("region", { name: "Choose image refs" });
  await expect(picker).toBeVisible();
  await picker.getByRole("button", { name: "Media" }).click();
  const first = picker.getByRole("button", { name: /^Attach / }).first();
  await expect(first).toBeVisible();
  await first.click();

  // The picture is in the row now, captioned by its position, with its own way off.
  const strip = page.locator("[data-mode-strip]");
  await expect(strip.getByText("Image 1")).toBeVisible();
  await expect(strip.getByRole("button", { name: /^Remove / })).toBeVisible();
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
