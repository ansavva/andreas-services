import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TokenizedPromptEditor, promptTriggerMatch } from "./TokenizedPromptEditor";
import type { PromptToken } from "./TokenizedPromptEditor";

const TOKENS: PromptToken[] = [
  { name: "block.face_only", kind: "block", hint: "THE FACE COMES FROM…" },
  { name: "block.scale_face", kind: "block", hint: "SCALE, held constant…" },
  { name: "character.top", kind: "computed" },
  // Still drawn as a pill, never offered — see `legacy` on the type.
  { name: "face_only", kind: "block", legacy: true },
  { name: "scale_face", kind: "block", legacy: true },
  { name: "top", kind: "computed", legacy: true },
];

function show(value: string, onValueChange = vi.fn()) {
  render(
    <TokenizedPromptEditor
      value={value}
      onValueChange={onValueChange}
      tokens={TOKENS}
      ariaLabel="Prompt"
    />,
  );
  return onValueChange;
}

afterEach(cleanup);

/**
 * **The invariant the whole component exists to protect.**
 *
 * Assembly is `string.Formatter().vformat` over `{name}`, and the fingerprint
 * hashes the prompt. An editor that normalised one space, or dropped one
 * trailing newline, would silently move every fingerprint — for a change
 * nobody made, on a payload nobody edited.
 */
it.each([
  ["a bare line", "A studio portrait of the person, front on."],
  ["one placeholder", "A studio portrait. {face_only} Neutral expression."],
  ["adjacent placeholders", "{scale_face}{face_only}"],
  ["paragraphs", "First line.\n\nSecond paragraph. {face_only}\n\nThird."],
  ["a computed value", "Wearing {top}. Flat mid-grey backdrop."],
  ["double spaces inside a line", "Two  spaces and {face_only}  after."],
  ["a placeholder at each end", "{face_only} middle {scale_face}"],
  ["the real face_front template",
   "A studio portrait of the person, front on, squared to the camera, looking " +
   "straight down the lens. Neutral expression, mouth closed. CROPPED AT " +
   "MID-CHEST — head and shoulders only, with no waist, no hips and no legs " +
   "anywhere in the frame.\n\n{scale_face}\n\n{face_only}\n\n{top}. " +
   "{backdrop_face} {light} {style} {quality}"],
])("round-trips %s byte for byte", async (_name, original) => {
  const changed = show(original);
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe(original);
});

it("draws a placeholder as a pill rather than as characters", async () => {
  show("A portrait. {face_only}");
  const pill = await waitFor(() => {
    const found = document.querySelector('[data-token="face_only"]');
    if (!found) throw new Error("no pill");
    return found as HTMLElement;
  });
  expect(pill.dataset.kind).toBe("block");
});

it("marks a COMPUTED value differently from a block", async () => {
  /**
   * A block is in the database and opens for editing; a computed value is
   * filled from the character's bible and has nothing behind it to open.
   * Identical pills would send somebody clicking `{top}` looking for a text box
   * that cannot exist.
   */
  show("Wearing {top} and {face_only}.");
  await waitFor(() => expect(document.querySelector('[data-token="top"]')).toBeTruthy());
  expect(
    (document.querySelector('[data-token="top"]') as HTMLElement).dataset.kind,
  ).toBe("computed");
  expect(
    (document.querySelector('[data-token="face_only"]') as HTMLElement).dataset.kind,
  ).toBe("block");
});

it("a placeholder nothing provides still round-trips, marked as unknown", async () => {
  /**
   * The editor must never silently drop or rewrite text it does not recognise.
   * `{no_such_block}` is a real failure the person needs to see and fix — but a
   * prompt that lost it on load would look repaired while the angle stayed
   * broken.
   */
  const changed = show("A portrait. {no_such_block}");
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe("A portrait. {no_such_block}");
});

/**
 * **The whole specification of when the menu appears.**
 *
 * Asserted on the matcher rather than through the menu, because opening the
 * real one needs a live caret and a DOM selection — jsdom has neither, and
 * `beforeinput` does not insert there. The menu itself, undo, and the caret are
 * covered in `e2e/prompt-editor.spec.ts`, in a real browser with a real
 * keyboard.
 */
it.each([
  ["a brace at the start of a line", "{", "", "{"],
  ["a name being typed", "{face", "face", "{face"],
  ["mid-paragraph, after a space", "…in the frame. {face", "face", "{face"],
  ["straight after a full stop", "text.{sc", "sc", "{sc"],
])("opens on %s", (_name, text, query, replaceable) => {
  const match = promptTriggerMatch(text);
  expect(match).not.toBeNull();
  expect(match!.matchingString).toBe(query);
  expect(match!.replaceableString).toBe(replaceable);
  expect(text.slice(match!.leadOffset)).toBe(replaceable);
});

it.each([
  ["there is no brace", "plain text"],
  ["the brace is already closed", "{face_only}"],
  ["the name has a space in it", "{face only"],
  ["the brace is doubled — that is a LITERAL brace", "a {{lit"],
])("stays shut when %s", (_name, text) => {
  expect(promptTriggerMatch(text)).toBeNull();
});

it("reports the query as the name alone, never the character before the brace", () => {
  /**
   * The regression this pins. The matcher grew a leading group to refuse `{{`,
   * and a second copy of the parse inside the menu plugin went on reading group
   * 1 — which had become the character BEFORE the brace. At the start of a node
   * the query was always empty so the list never narrowed; mid-paragraph it was
   * the preceding space, which names no placeholder, so no menu opened at all.
   */
  expect(promptTriggerMatch(" {face")!.matchingString).toBe("face");
  expect(promptTriggerMatch(".{face")!.matchingString).toBe("face");
});

it("turns a hand-typed placeholder into a pill, so the menu is not the only way in", async () => {
  /**
   * `Hydrate` puts the stored string in as plain TEXT and one transform turns
   * it into pills — the same transform a typed `{light}` goes through. That is
   * why this can be asserted on a loaded value: there is no second parse for
   * the typing path to drift from.
   */
  show("Lit by {face_only} and nothing else.");
  await waitFor(() =>
    expect(document.querySelector('[data-token="face_only"]')).toBeTruthy(),
  );
});

it("leaves a DOUBLED brace as text, because it is a literal", async () => {
  /**
   * `assemble` says a literal brace is written `{{` and `}}`. Drawing one as a
   * pill would claim the prompt cites something it does not.
   */
  const changed = show("Write {{face_only}} literally.");
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe("Write {{face_only}} literally.");
  expect(document.querySelector('[data-token="face_only"]')).toBeNull();
});

it.each([
  ["a namespaced block", "A portrait. {block.face_only} Neutral."],
  ["a namespaced character value", "Wearing {character.top}."],
  ["both spellings in one template", "{face_only} and {block.face_only}"],
])("round-trips %s byte for byte", async (_name, original) => {
  const changed = show(original);
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe(original);
});

it("draws a namespaced placeholder as ONE pill, dot and all", async () => {
  show("A portrait. {block.face_only}");
  const pill = await waitFor(() => {
    const found = document.querySelector('[data-token="block.face_only"]');
    if (!found) throw new Error("no pill");
    return found as HTMLElement;
  });
  expect(pill.dataset.kind).toBe("block");
  expect(pill.textContent).toBe("{block.face_only}");
});

it("still draws the LEGACY bare spelling as the block it is", async () => {
  /**
   * Every template written before the namespaces uses it. Drawn as an unknown
   * value, all of them would read as broken.
   */
  show("A portrait. {face_only}");
  await waitFor(() =>
    expect(
      (document.querySelector('[data-token="face_only"]') as HTMLElement).dataset.kind,
    ).toBe("block"),
  );
});

it("opens on a dotted name and narrows on the part after the dot", () => {
  expect(promptTriggerMatch("{block.face")!.matchingString).toBe("block.face");
  expect(promptTriggerMatch("text. {character.")!.matchingString).toBe("character.");
});
