/**
 * The prompt editor, driven by a real keyboard.
 *
 * **These specs exist because jsdom cannot hold a caret.** Lexical reads the DOM
 * selection to decide where text goes and when the placeholder menu opens, and
 * jsdom has no selection to read — a `beforeinput` dispatched there inserts
 * nothing at all. So the vitest suite covers the round trip, the pills and the
 * trigger regex, and everything that needs somewhere for the cursor to BE is
 * here.
 *
 * Every one of these is a bug that shipped.
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

/** The first angle's prompt box, with the caret put at the end of its first paragraph. */
async function prompt(page: import("@playwright/test").Page) {
  await page.goto("/reference-spec");
  const box = page.getByLabel("Prompt for face_front");
  await expect(box).toBeVisible();
  await box.click();
  // `ControlOrMeta+ArrowDown` would leave the paragraph; End is the end of the
  // visual line the click landed on, which is where somebody types.
  await page.keyboard.press("End");
  return box;
}

test("the caret stays where you put it as you type", async ({ page }) => {
  /**
   * **The bug this is really about.** The editor is controlled: it emits, the
   * page stores, and the stored string arrives back as a prop one render later.
   * That echo was indistinguishable from a value changed by somebody else, so
   * every keystroke tore the document down and rebuilt it — and the caret went
   * to the top of the box on each one. Five characters came out reversed and at
   * the wrong end, and the box was unusable for anything longer than a word.
   */
  const box = await prompt(page);
  await page.keyboard.type("ABCDE");
  await expect(box).toContainText("ABCDE");
});

test("undo takes back what was typed", async ({ page }) => {
  /**
   * Lexical ships no history unless it is asked for, so Cmd-Z did nothing at
   * all — in a box whose whole purpose is trying wordings out.
   */
  const box = await prompt(page);
  await page.keyboard.type(" DELETE ME");
  await expect(box).toContainText("DELETE ME");
  await page.keyboard.press("ControlOrMeta+z");
  await expect(box).not.toContainText("DELETE ME");
});

test("`{` opens the menu and NARROWS it as the name is typed", async ({ page }) => {
  /**
   * Two bugs. The trigger was `+`, a key nobody can guess with nothing on the
   * page to name it. And a second copy of the trigger parse read the wrong
   * capture group once the regex grew a guard for `{{`, so the query was the
   * character before the brace: empty at the start of a line, which left the
   * list unfiltered, and a SPACE mid-paragraph, which matches no placeholder at
   * all and so opened nothing.
   */
  await prompt(page);
  await page.keyboard.type(" {");
  const menu = page.getByRole("listbox", { name: /placeholder/i });
  await expect(menu).toBeVisible();
  const all = await menu.getByRole("option").count();

  await page.keyboard.type("face");
  await expect(menu.getByRole("option")).not.toHaveCount(all);
  for (const name of await menu.getByRole("option").allTextContents()) {
    expect(name).toContain("face");
  }
});

/**
 * A block `face_front` does NOT already cite, so a count of one means the pill
 * that was just inserted. `{face_only}` and `{quality}` are in that template
 * already, and asserting one of those counts the template's own pill.
 */
const UNCITED = "minimal";

test("choosing from the menu inserts a NAMESPACED pill and no stray brace", async ({
  page,
}) => {
  /**
   * The menu offers `{block.x}` rather than the bare `{x}`: a bare name is one
   * flat namespace shared with the character's bible, where a block called
   * `top` silently lost. Nothing new should be written in that spelling.
   */
  const box = await prompt(page);
  await page.keyboard.type(` {block.${UNCITED.slice(0, 4)}`);
  await page.getByRole("option", { name: new RegExp(UNCITED) }).first().click();

  await expect(box.locator(`[data-token="block.${UNCITED}"]`)).toHaveCount(1);
  // The brace and the half-typed name are consumed by the insertion, not left
  // sitting in front of the pill.
  await expect(box).not.toContainText(`{block.${UNCITED.slice(0, 4)}{`);
});

test("a placeholder typed out in full becomes a pill by itself", async ({ page }) => {
  /**
   * The menu is the shortcut, not the entrance. When it was the only way in,
   * anyone who did not know the trigger could not insert one at all.
   */
  const box = await prompt(page);
  await page.keyboard.type(` {${UNCITED}}`);
  await expect(box.locator(`[data-token="${UNCITED}"]`)).toHaveCount(1);
});

test("dismissing the menu leaves what was typed, rather than eating it", async ({ page }) => {
  /**
   * The hand-rolled menu held the query in React state and threw the trigger
   * away, so everything typed after an accidental trigger went somewhere
   * invisible. Here the text is real text throughout.
   */
  const box = await prompt(page);
  await page.keyboard.type(" {zzz");
  await page.keyboard.press("Escape");
  await expect(box).toContainText("{zzz");
});

test("the preview writes each block out and says which block it was", async ({ page }) => {
  await page.goto("/reference-spec");
  const preview = page.getByLabel("Assembled preview").first();
  await expect(preview).toBeVisible();
  // The prose of a block the template only CITES.
  await expect(preview).toContainText("SCALE, held constant");
  await expect(preview.locator('[data-block="scale_face"]')).toHaveCount(1);
});

test("the blocks live on their own tab", async ({ page }) => {
  await page.goto("/reference-spec");
  await expect(page.getByRole("button", { name: /\{scale_face\}/ })).toHaveCount(0);
  await page.getByRole("tab", { name: /Blocks/ }).click();
  await expect(page.getByRole("button", { name: /\{scale_face\}/ })).toHaveCount(1);
});

test("a block can be closed again after it is opened", async ({ page }) => {
  await page.goto("/reference-spec");
  await page.getByRole("tab", { name: /Blocks/ }).click();
  // By `aria-expanded`, not by name: the delete control inside an opened block
  // names the block too, so a name match is ambiguous the moment it opens.
  const header = page
    .locator("button[aria-expanded]")
    .filter({ hasText: "{build_intro}" });

  await header.click();
  const box = page.getByRole("textbox").filter({ hasText: /THE BUILD IS/ });
  await expect(box).toHaveCount(1);

  await header.click();
  await expect(box).toHaveCount(0);
});

test("Close and Escape both get you out of an opened block", async ({ page }) => {
  await page.goto("/reference-spec");
  await page.getByRole("tab", { name: /Blocks/ }).click();
  // By `aria-expanded`, not by name: the delete control inside an opened block
  // names the block too, so a name match is ambiguous the moment it opens.
  const header = page
    .locator("button[aria-expanded]")
    .filter({ hasText: "{build_intro}" });
  const box = page.getByRole("textbox").filter({ hasText: /THE BUILD IS/ });

  await header.click();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(box).toHaveCount(0);

  await header.click();
  await box.press("Escape");
  await expect(box).toHaveCount(0);
});
