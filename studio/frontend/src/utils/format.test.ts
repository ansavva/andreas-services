import { describe, expect, it } from "vitest";

import { humaniseKey } from "./format";

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
