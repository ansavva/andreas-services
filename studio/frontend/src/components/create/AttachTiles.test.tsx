import { describe, expect, it } from "vitest";

import type { Attachment } from "../../context/CreateBarContext";
import type { ModelEntry } from "../../types";
import { fallbackDropRole } from "./AttachTiles";

const STILL: ModelEntry = {
  key: "still",
  model: "v/still",
  kind: "image",
  skill: "studio-media-still",
  images: { refs: "input_images", start: null, end: null, max_refs: 2 },
  snapshot: { refreshed: "2026-08-15" },
};

const MOTION: ModelEntry = {
  key: "motion",
  model: "v/motion",
  kind: "video",
  skill: "studio-media-motion",
  images: { refs: null, start: "start_image", end: "end_image" },
  snapshot: { refreshed: "2026-08-15" },
};

const held = (role: Attachment["role"], node = `node-${role}`): Attachment => ({
  ref: { node, kind: "object" },
  role,
});

/**
 * Where a drop on the sheet that named no tile goes: a reference while the
 * model has room for one, then the first frame the model takes and does not
 * yet hold, and nowhere once every role is full.
 */
describe("fallbackDropRole", () => {
  it("is a reference until the cap, then nothing", () => {
    expect(fallbackDropRole("image", STILL, [])).toBe("reference");
    expect(fallbackDropRole("image", STILL, [held("reference")])).toBe("reference");
    expect(
      fallbackDropRole("image", STILL, [held("reference", "a"), held("reference", "b")]),
    ).toBeNull();
  });

  it("falls through the frames a video model takes, one picture each", () => {
    expect(fallbackDropRole("video", MOTION, [])).toBe("start");
    expect(fallbackDropRole("video", MOTION, [held("start")])).toBe("end");
    expect(fallbackDropRole("video", MOTION, [held("start"), held("end")])).toBeNull();
  });
});
