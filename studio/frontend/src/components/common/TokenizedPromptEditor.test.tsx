import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TokenizedPromptEditor, promptTriggerMatch } from "./TokenizedPromptEditor";
import type { PromptToken } from "./TokenizedPromptEditor";

const TOKENS: PromptToken[] = [
  { name: "block.face_only", kind: "block", hint: "THE FACE COMES FROM…" },
  { name: "block.scale_face", kind: "block", hint: "SCALE, held constant…" },
  { name: "block.light", kind: "block", hint: "SOFT, even light…" },
  { name: "character.1.top", kind: "computed" },
  { name: "slot.identity", kind: "computed" },
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

function pill(name: string): HTMLElement | null {
  return document.querySelector(`[data-token="${name}"]`);
}

afterEach(cleanup);

/**
 * **The invariant the whole component exists to protect.**
 *
 * The API fills by scanning for `@name`, and the fingerprint hashes the
 * prompt. An editor that normalised one space, or dropped one trailing
 * newline, would silently move every fingerprint — for a change nobody made,
 * on a payload nobody edited.
 */
it.each([
  ["a bare line", "A studio portrait of the person, front on."],
  ["one citation", "A studio portrait. @block.face_only Neutral expression."],
  ["adjacent citations", "@block.scale_face @block.face_only"],
  ["paragraphs", "First line.\n\nSecond paragraph. @block.face_only\n\nThird."],
  ["a computed value", "Wearing @character.1.top. Flat mid-grey backdrop."],
  ["double spaces inside a line", "Two  spaces and @block.face_only  after."],
  ["a citation at each end", "@block.face_only middle @block.scale_face"],
  ["a citation at the end of a line, before a break", "@block.light\nnext line"],
  ["an e-mail address and shorthand", "mail me@block.light, shot @ f/2.8"],
  ["the real face_front template",
   "A studio portrait of the person, front on, squared to the camera, looking " +
   "straight down the lens. Neutral expression, mouth closed. CROPPED AT " +
   "MID-CHEST — head and shoulders only, with no waist, no hips and no legs " +
   "anywhere in the frame.\n\n@block.scale_face\n\n@block.face_only\n\n@character.1.top. " +
   "@block.light @slot.identity"],
])("round-trips %s byte for byte", async (_name, original) => {
  const changed = show(original);
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe(original);
});

/**
 * **The bug this pins.** `Pillify` re-registers its transform whenever the
 * known names change, and Lexical marks the existing nodes dirty in an
 * update tagged `history-merge`. A value loaded in the same render merged
 * into that update, inherited the tag, and the change plugin skipped it —
 * so nothing recorded the new text, and the NEXT value equal to the stale
 * record was treated as already shown. In the app: Edit on run A, then B,
 * then A again drew B's prompt over A's plan.
 */
it("shows each loaded value even when the known names change with it", async () => {
  const changed = vi.fn();
  const { rerender } = render(
    <TokenizedPromptEditor value="Run A." onValueChange={changed} tokens={TOKENS} ariaLabel="Prompt" />,
  );
  const box = () => document.querySelector('[role="textbox"]')!;
  await waitFor(() => expect(box().textContent).toBe("Run A."));

  // Run B loads with a different cast, so the token list moves with the text.
  rerender(
    <TokenizedPromptEditor
      value="Run B."
      onValueChange={changed}
      tokens={[...TOKENS, { name: "character.2.top", kind: "computed" }]}
      ariaLabel="Prompt"
    />,
  );
  await waitFor(() => expect(box().textContent).toBe("Run B."));

  // Back to A: the box must say A, not keep B.
  rerender(
    <TokenizedPromptEditor value="Run A." onValueChange={changed} tokens={TOKENS} ariaLabel="Prompt" />,
  );
  await waitFor(() => expect(box().textContent).toBe("Run A."));
});

it("draws a citation as a pill rather than as characters", async () => {
  show("A portrait. @block.face_only");
  const found = await waitFor(() => {
    const got = pill("block.face_only");
    if (!got) throw new Error("no pill");
    return got;
  });
  expect(found.dataset.namespace).toBe("block");
  expect(found.textContent).toBe("@block.face_only");
});

it("marks a pill with its NAMESPACE — block, character, slot", async () => {
  /**
   * A block is in the database and opens for editing; a character value is
   * filled from the bible and has nothing behind it to open; a slot is where
   * the images landed. Identical pills would send somebody clicking
   * `@character.1.top` looking for a text box that cannot exist — so a block
   * is the full tint at medium weight and a computed value is stepped back,
   * and the text says the namespace too.
   */
  show("Wearing @character.1.top and @block.face_only, @slot.identity.");
  await waitFor(() => expect(pill("character.1.top")).toBeTruthy());
  expect(pill("character.1.top")!.dataset.namespace).toBe("character");
  expect(pill("block.face_only")!.dataset.namespace).toBe("block");
  expect(pill("slot.identity")!.dataset.namespace).toBe("slot");
  expect(pill("character.1.top")!.className).not.toBe(pill("block.face_only")!.className);
});

it("a citation nothing provides still round-trips, and is not a pill", async () => {
  /**
   * The editor must never silently drop or rewrite text it does not recognise.
   * `@block.no_such_block` is a real failure the person needs to see and fix —
   * but a prompt that lost it on load would look repaired while the template
   * stayed broken. It stays TEXT rather than becoming a pill: an `@` has no
   * closing brace to say the name is finished, so only a name the editor
   * knows is one somebody meant. The template page names it in its warning.
   */
  const changed = show("A portrait. @block.no_such_block");
  await waitFor(() => expect(changed).toHaveBeenCalled());
  expect(changed.mock.calls.at(-1)![0]).toBe("A portrait. @block.no_such_block");
  expect(pill("block.no_such_block")).toBeNull();
});

it("leaves an `@` inside a word alone", async () => {
  /** `me@block.light` is an address. The boundary is `CITATION`'s own. */
  show("mail me@block.light please");
  await waitFor(() => expect(document.querySelector("[aria-label=Prompt]")).toBeTruthy());
  expect(pill("block.light")).toBeNull();
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
  ["an @ at the start of a line", "@", "", "@"],
  ["a name being typed", "@face", "face", "@face"],
  ["mid-paragraph, after a space", "…in the frame. @face", "face", "@face"],
  ["straight after a full stop", "text.@sc", "sc", "@sc"],
])("opens on %s", (_name, text, query, replaceable) => {
  const match = promptTriggerMatch(text);
  expect(match).not.toBeNull();
  expect(match!.matchingString).toBe(query);
  expect(match!.replaceableString).toBe(replaceable);
  expect(text.slice(match!.leadOffset)).toBe(replaceable);
});

it.each([
  ["there is no @", "plain text"],
  ["the name has a space in it", "@face only"],
  ["the @ is inside a word — an address, not a mention", "mail me@lit"],
])("stays shut when %s", (_name, text) => {
  expect(promptTriggerMatch(text)).toBeNull();
});

it("reports the query as the name alone, never the character before the @", () => {
  /**
   * The regression this pins. The matcher grew a leading group for the word
   * boundary, and a second copy of the parse inside the menu plugin went on
   * reading group 1 — which had become the character BEFORE the trigger. At
   * the start of a node the query was always empty so the list never
   * narrowed; mid-paragraph it was the preceding space, which names no
   * placeholder, so no menu opened at all.
   */
  expect(promptTriggerMatch(" @face")!.matchingString).toBe("face");
  expect(promptTriggerMatch(".@face")!.matchingString).toBe("face");
});

it("turns a hand-typed citation into a pill, so the menu is not the only way in", async () => {
  /**
   * `Hydrate` puts the stored string in as plain TEXT and one transform turns
   * it into pills — the same transform a typed `@block.light` goes through.
   * That is why this can be asserted on a loaded value: there is no second
   * parse for the typing path to drift from.
   */
  show("Lit by @block.face_only and nothing else.");
  await waitFor(() => expect(pill("block.face_only")).toBeTruthy());
});

it("draws a dotted name as ONE pill, dots and all", async () => {
  show("A portrait. @character.1.top");
  const found = await waitFor(() => {
    const got = pill("character.1.top");
    if (!got) throw new Error("no pill");
    return got;
  });
  expect(found.textContent).toBe("@character.1.top");
});

it("a citation ends where its name does — the full stop after it is prose", async () => {
  const changed = show("Then @block.light. Done.");
  await waitFor(() => expect(pill("block.light")).toBeTruthy());
  expect(pill("block.light")!.textContent).toBe("@block.light");
  expect(changed.mock.calls.at(-1)![0]).toBe("Then @block.light. Done.");
});

it("opens on a dotted name and narrows on the part after the dot", () => {
  expect(promptTriggerMatch("@block.face")!.matchingString).toBe("block.face");
  expect(promptTriggerMatch("text. @character.")!.matchingString).toBe("character.");
});
