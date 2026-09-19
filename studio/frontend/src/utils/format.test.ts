import { describe, expect, it } from "vitest";

import { describeFolder, humaniseKey } from "./format";

/**
 * One label rule for every snake_case key this app draws — a model's schema
 * prop, a character bible's section, a camera field. Plain words become
 * sentence case; a known unit or acronym keeps its own shape rather than
 * being sentence-cased into something a model's docs would not recognise.
 */
describe("humaniseKey", () => {
  it("sentence-cases a plain key", () => {
    expect(humaniseKey("apparent_age")).toBe("Apparent age");
    expect(humaniseKey("aspect_ratio")).toBe("Aspect ratio");
    expect(humaniseKey("number_of_images")).toBe("Number of images");
  });

  it("keeps a single word capitalised and nothing else", () => {
    expect(humaniseKey("shot")).toBe("Shot");
    expect(humaniseKey("movement")).toBe("Movement");
    expect(humaniseKey("speed")).toBe("Speed");
  });

  it("puts a trailing unit in parens rather than capitalising it", () => {
    expect(humaniseKey("lens_mm")).toBe("Lens (mm)");
  });

  it("uppercases a bare acronym", () => {
    expect(humaniseKey("fps")).toBe("FPS");
    expect(humaniseKey("id")).toBe("ID");
    expect(humaniseKey("url")).toBe("URL");
  });

  it("uppercases an acronym inside a compound key", () => {
    expect(humaniseKey("run_id")).toBe("Run ID");
    expect(humaniseKey("video_url")).toBe("Video URL");
  });

  it("leaves an empty key alone", () => {
    expect(humaniseKey("")).toBe("");
  });
});

/**
 * An entity's root folder is stored under the entity's id. The row shows the
 * entity's name and kind instead, and only when the folder IS the root — a
 * folder inside a character carries the same `owner` and keeps its own name.
 */
describe("describeFolder", () => {
  it("titles an entity root by its owner's name, with the kind as the caption", () => {
    expect(
      describeFolder("char-1111", { kind: "character", id: "char-1111", name: "Dev Subject" }),
    ).toEqual({ title: "Dev Subject", subtitle: "character" });
    expect(
      describeFolder("proj-2222", { kind: "project", id: "proj-2222", name: "Spring shoot" }),
    ).toEqual({ title: "Spring shoot", subtitle: "project" });
  });

  it("keeps the id when the owner has no name, and still says what it is", () => {
    expect(describeFolder("run-3333", { kind: "run", id: "run-3333", name: null })).toEqual({
      title: "run-3333",
      subtitle: "run",
    });
  });

  it("leaves a folder inside an entity under its own name", () => {
    expect(
      describeFolder("reference", { kind: "character", id: "char-1111", name: "Dev Subject" }),
    ).toEqual({ title: "reference" });
  });

  it("splits a pipeline run folder into a slug and a timestamp", () => {
    expect(describeFolder("2026-08-15_01-00-30_pullup-originals")).toEqual({
      title: "pullup-originals",
      subtitle: "2026-08-15 01:00:30",
    });
    expect(describeFolder("2026-08-15_01-00-30_pullup-originals", null)).toEqual({
      title: "pullup-originals",
      subtitle: "2026-08-15 01:00:30",
    });
  });

  it("leaves anything else exactly as it is", () => {
    expect(describeFolder("input")).toEqual({ title: "input" });
  });
});
