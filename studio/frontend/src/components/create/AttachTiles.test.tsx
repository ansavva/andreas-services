import { describe, expect, it } from "vitest";

import type { Attachment } from "../../context/CreateBarContext";
import type { ModelEntry } from "../../types";
import { holdsOne } from "../../context/CreateBarContext";
import { fallbackDropRole } from "./AttachTiles";
import { ROLES_BY_KIND, fieldFor, sendsOf } from "./roles";

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

/** Kling on fal: subjects rather than a flat reference list, and a voice. */
const ELEMENTS: ModelEntry = {
  key: "fal-kling-v3-i2v",
  model: "fal/fal-ai/kling-video/v3/pro/image-to-video",
  kind: "video",
  skill: "studio-media-fal-kling",
  images: { refs: "elements", start: "start_image_url", end: "end_image_url", max_refs: 4 },
  elements: { field: "elements", frontal: "frontal_image_url",
              refs: "reference_image_urls", voice: "voice_id", max: 4 },
  audio: { voice: "elements", accepts_ext: [".mp3", ".wav"] },
  snapshot: { refreshed: "2026-09-22" },
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

/**
 * A voice is bound to a SUBJECT, not to the run — the id the provider reads
 * sits inside that subject's element, beside its pictures. So the role exists
 * only on the models whose entry declares an `audio.voice`, and it lands on
 * the same field the references do.
 */
describe("the voice role", () => {
  it("binds to the elements field, and to nothing on a model without one", () => {
    expect(fieldFor("voice", ELEMENTS)).toBe("elements");
    expect(fieldFor("voice", MOTION)).toBeNull();
    expect(fieldFor("voice", TRANSFER)).toBeNull();
  });

  it("is a video role, offered last", () => {
    expect(ROLES_BY_KIND.video).toContain("voice");
    expect(ROLES_BY_KIND.image).not.toContain("voice");
  });

  it("accumulates, because a scene can have two people speaking in it", () => {
    expect(holdsOne("voice")).toBe(false);
    expect(holdsOne("start")).toBe(true);
  });

  it("travels as a send that says it is a voice", () => {
    const sends = sendsOf([held("reference"), held("voice")], ELEMENTS);
    expect(sends).toEqual([
      { field: "elements", role: "reference", node: "node-reference" },
      { field: "elements", role: "voice", node: "node-voice" },
    ]);
  });

  it("is dropped rather than sent to a model that cannot speak", () => {
    expect(sendsOf([held("voice")], MOTION)).toEqual([]);
  });

  it("never takes a dropped still, which is what a drag carries", () => {
    expect(fallbackDropRole("video", ELEMENTS, [])).not.toBe("voice");
  });
});
