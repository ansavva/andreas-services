import { describe, expect, it } from "vitest";

import { blockNamed, citationsIn, citesTemplate } from "./citations";

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
    expect(citesTemplate("A portrait. @block.face_only")).toBe(true);
    expect(citesTemplate("Wearing @character.1.top.")).toBe(true);
    expect(citesTemplate("Identity is @slot.identity.")).toBe(true);
  });

  it("is true for a character value that names a variant", () => {
    expect(citesTemplate("@character.2.build.face")).toBe(true);
    expect(citesTemplate("@character.10.must.body")).toBe(true);
  });

  it("is true for the spellings the API refuses by name", () => {
    /**
     * `@character.top` has no position and `@character.1.build` no variant, so
     * neither resolves — but both are unmistakably an attempt to cite a
     * character, and the useful answer is the API's sentence saying how to spell
     * it. Treated as prose they would reach the model as written.
     */
    expect(citesTemplate("@character.top")).toBe(true);
    expect(citesTemplate("@character.1.build")).toBe(true);
  });

  it("is FALSE for a prompt written as JSON", () => {
    const prompt =
      '{"subject": "a person at a window", "camera": {"move": "push in"}}';
    expect(citesTemplate(prompt)).toBe(false);
  });

  it("is false for an @ that is not a mention", () => {
    /** Shorthand, a bare handle, an address: prose, all three. */
    expect(citesTemplate("shot @ f/2.8")).toBe(false);
    expect(citesTemplate("@")).toBe(false);
    expect(citesTemplate("mail me@block.example")).toBe(false);
  });

  it("is false for an @ naming no namespace", () => {
    /** A bare `@face_only` and a mistyped `@blocks.face_only` are both text. */
    expect(citesTemplate("@face_only")).toBe(false);
    expect(citesTemplate("@blocks.face_only")).toBe(false);
    expect(citesTemplate("@wardrobe.top")).toBe(false);
  });

  it("is false for the brace spelling, which the API rewrites before the app sees it", () => {
    expect(citesTemplate("{block.face_only}")).toBe(false);
  });

  it("finds a citation inside a JSON prompt", () => {
    expect(citesTemplate('{"subject": "@character.1.top"}')).toBe(true);
  });
});

describe("citationsIn", () => {
  it("returns each citation with its namespace and where it sits", () => {
    const text = "A. @block.face_only B @character.1.top.";
    expect(citationsIn(text)).toEqual([
      { name: "block.face_only", namespace: "block", start: 3, end: 19 },
      { name: "character.1.top", namespace: "character", start: 22, end: 38 },
    ]);
    expect(text.slice(22, 38)).toBe("@character.1.top");
  });

  it("ends a citation where its name does", () => {
    /** No closing brace: a full stop is the sentence's, a variant is the name's. */
    expect(citationsIn("@block.light.").map((c) => c.name)).toEqual(["block.light"]);
    expect(citationsIn("@character.1.build.face.").map((c) => c.name)).toEqual([
      "character.1.build.face",
    ]);
    expect(citationsIn("@character.1.top.then").map((c) => c.name)).toEqual([
      "character.1.top",
    ]);
  });
});

describe("blockNamed", () => {
  it("names the block a citation points at, and nothing for a computed value", () => {
    expect(blockNamed("block.face_only")).toBe("face_only");
    expect(blockNamed("character.1.top")).toBeNull();
    expect(blockNamed("slot.identity")).toBeNull();
  });
});
