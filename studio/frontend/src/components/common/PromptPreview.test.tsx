import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { PromptPreview } from "./PromptPreview";

const BLOCKS = {
  face_only: "THE FACE COMES FROM THE REFERENCE IMAGES.",
  light: "Soft frontal key with gentle falloff.",
};

afterEach(cleanup);

function box() {
  return screen.getByLabelText("Assembled preview");
}

/**
 * The preview's text WITHOUT the little `{name}` labels it puts in front of
 * each expanded block — so these tests still assert on the prose, which is the
 * thing that has to match what the pipeline assembles.
 */
function unlabelled() {
  const clone = box().cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-label]").forEach((label) => label.remove());
  return clone.textContent;
}

it("writes a cited block out in place", () => {
  render(<PromptPreview prompt="A portrait. {face_only} Neutral." blocks={BLOCKS} />);
  expect(unlabelled()).toBe("A portrait. THE FACE COMES FROM THE REFERENCE IMAGES. Neutral.");
});

it("says which block each stretch of expanded prose came from", () => {
  /**
   * Unlabelled, the preview is a wall of text and the question it exists to
   * answer — which of these words can I go and change — has no answer in it.
   */
  render(<PromptPreview prompt="A portrait. {face_only}" blocks={BLOCKS} />);
  const expanded = document.querySelector('[data-block="face_only"]') as HTMLElement;
  expect(expanded.textContent).toBe(
    "{block.face_only}THE FACE COMES FROM THE REFERENCE IMAGES.",
  );
});

it("keeps blank lines, because they are what the model reads as structure", () => {
  render(<PromptPreview prompt={"One.\n\n{light}\n\nThree."} blocks={BLOCKS} />);
  expect(unlabelled()).toBe("One.\n\nSoft frontal key with gentle falloff.\n\nThree.");
});

it("shows a value the character fills as a hole rather than dropping it", () => {
  /**
   * Dropping it would show a sentence the model never sees; expanding it would
   * need the bible, which is `reference.py`'s job and must stay its only one.
   */
  render(<PromptPreview prompt="Wearing {top}. {light}" blocks={BLOCKS} />);
  expect(unlabelled()).toBe("Wearing {top}. Soft frontal key with gentle falloff.");
  expect(screen.getByText("{top}").className).toContain("border-dashed");
});

it("expands ONE pass, exactly as assemble does", () => {
  /**
   * `assemble` is a single `vformat`, so a block citing another block is not
   * expanded there. Expanding it here would preview a prompt the pipeline
   * cannot produce.
   */
  render(
    <PromptPreview
      prompt="{outer}"
      blocks={{ outer: "sees {light} unexpanded", light: "SOFT" }}
    />,
  );
  expect(unlabelled()).toBe("sees {light} unexpanded");
});

it("leaves a doubled brace alone, because it is a literal", () => {
  render(<PromptPreview prompt="Use {{light}} literally." blocks={BLOCKS} />);
  expect(unlabelled()).toBe("Use {{light}} literally.");
});

it("expands a NAMESPACED block, and leaves the character's values as holes", () => {
  /**
   * `{block.x}` is the same block as the legacy `{x}`. `{character.top}` and
   * `{slot.angle}` are filled at shoot time, and this screen has no character —
   * so they stay the holes they are rather than being dropped.
   */
  render(
    <PromptPreview
      prompt="{block.face_only} Wearing {character.top}. {slot.angle}"
      blocks={BLOCKS}
    />,
  );
  expect(unlabelled()).toBe(
    "THE FACE COMES FROM THE REFERENCE IMAGES. Wearing {character.top}. {slot.angle}",
  );
  expect(document.querySelector('[data-block="face_only"]')).toBeTruthy();
});

it("does not treat a block called `top` as the character's", () => {
  /**
   * The collision this spelling exists to end. Bare, the two were one flat
   * namespace and the bible silently won.
   */
  render(
    <PromptPreview
      prompt="{block.top} :: {character.top}"
      blocks={{ ...BLOCKS, top: "A BLOCK CALLED TOP" }}
    />,
  );
  expect(unlabelled()).toBe("A BLOCK CALLED TOP :: {character.top}");
});
