import { describe, expect, it } from "vitest";

import { citesTemplate } from "./citations";

/**
 * The test that decides whether a prompt is sent as a template.
 *
 * It was `prompt.includes("{")`, which made a JSON prompt unsendable from the
 * app: `studio prompt` writes one as a serialised object, so every structured
 * prompt went out as a template and came back refused for citing `{ "subject"}`.
 * The shapes below are the whole rule, and `services/template.py` fills by the
 * same one.
 */
describe("citesTemplate", () => {
  it("is true for each of the three namespaces", () => {
    expect(citesTemplate("A portrait. {block.face_only}")).toBe(true);
    expect(citesTemplate("Wearing {character.1.top}.")).toBe(true);
    expect(citesTemplate("Identity is {slot.identity}.")).toBe(true);
  });

  it("is true for a character value that names a variant", () => {
    expect(citesTemplate("{character.2.build.face}")).toBe(true);
    expect(citesTemplate("{character.10.must.body}")).toBe(true);
  });

  it("is true for the spellings the API refuses by name", () => {
    /**
     * `{character.top}` has no position and `{character.1.build}` no variant, so
     * neither resolves — but both are unmistakably an attempt to cite a
     * character, and the useful answer is the API's sentence saying how to spell
     * it. Treated as prose they would reach the model as braces.
     */
    expect(citesTemplate("{character.top}")).toBe(true);
    expect(citesTemplate("{character.1.build}")).toBe(true);
  });

  it("is FALSE for a prompt written as JSON", () => {
    const prompt =
      '{"subject": "a person at a window", "camera": {"move": "push in"}}';
    expect(citesTemplate(prompt)).toBe(false);
  });

  it("is false for a stray brace in prose", () => {
    expect(citesTemplate("a { b")).toBe(false);
    expect(citesTemplate("a } b")).toBe(false);
    expect(citesTemplate("{}")).toBe(false);
    expect(citesTemplate("set { of things }")).toBe(false);
  });

  it("is false for a brace naming no namespace", () => {
    /** A bare `{face_only}` and a mistyped `{blocks.face_only}` are both text. */
    expect(citesTemplate("{face_only}")).toBe(false);
    expect(citesTemplate("{blocks.face_only}")).toBe(false);
    expect(citesTemplate("{wardrobe.top}")).toBe(false);
  });

  it("finds a citation inside a JSON prompt", () => {
    expect(citesTemplate('{"subject": "{character.1.top}"}')).toBe(true);
  });
});
