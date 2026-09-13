import { describe, expect, it } from "vitest";

import type { Attachment } from "../../context/CreateBarContext";
import type { ModelEntry } from "../../types";
import { fallbackDropRole } from "./AttachTiles";
import { fieldFor, sendsOf } from "./roles";

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

/** A motion-transfer model: one still, one clip, nothing else. */
const TRANSFER: ModelEntry = {
  key: "transfer",
  model: "v/transfer",
  kind: "video",
  skill: "studio-media-transfer",
  images: { refs: null, start: "image", end: null, max_refs: 0 },
  clips: { source: "video", accepts_ext: [".mp4", ".mov"] },
  snapshot: { refreshed: "2026-09-12" },
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

  it("never lands a dropped still on the clip", () => {
    expect(fallbackDropRole("video", TRANSFER, [])).toBe("start");
    expect(fallbackDropRole("video", TRANSFER, [held("start")])).toBeNull();
  });
});

/**
 * The clip is the one video a model works from. It binds to the field the
 * registry names under `clips.source`, and a model that names none has no
 * such role — the tile is hidden and an attachment in that role is dropped.
 */
describe("the clip role", () => {
  it("binds to the registry's clip field, and to nothing on a model without one", () => {
    expect(fieldFor("clip", TRANSFER)).toBe("video");
    expect(fieldFor("clip", MOTION)).toBeNull();
  });

  it("travels as a send with its role", () => {
    const sends = sendsOf([held("start"), held("clip")], TRANSFER);
    expect(sends).toEqual([
      { field: "image", role: "start", node: "node-start" },
      { field: "video", role: "clip", node: "node-clip" },
    ]);
    expect(sendsOf([held("clip")], MOTION)).toEqual([]);
  });

  it("never sends a placeholder — a pending ref names nothing yet", () => {
    const waiting: Attachment = {
      ref: { node: "pending-1", kind: "object", pending: "Taking the first frame of a.mp4…" },
      role: "start",
    };
    expect(sendsOf([waiting, held("clip")], TRANSFER)).toEqual([
      { field: "video", role: "clip", node: "node-clip" },
    ]);
  });
});
