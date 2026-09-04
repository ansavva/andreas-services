import { describe, expect, it } from "vitest";

import { rerunBodyOf } from "./rerun";
import type { RunRecord, RunSend } from "../../types";

/**
 * What a re-run copies, and — the part worth pinning — what it refuses to add.
 *
 * The failure these guard against is silent in both directions: a send that
 * carries its derived half back would assert a provenance nobody worked out,
 * and a plan that gained a note would move the fingerprint, so two identical
 * submissions would stop looking identical to the duplicate check.
 */

function send(over: Partial<RunSend> = {}): RunSend {
  return {
    order: 1,
    field: "image_input",
    role: "reference",
    node: "node-1",
    name: "front.webp",
    size: 91_234,
    content_type: "image/webp",
    url: "https://example.test/front.webp?X-Amz-Signature=abc",
    source: { kind: "character", character: "subject-a", group: "face" },
    ...over,
  } as RunSend;
}

function record(over: Partial<RunRecord> = {}): RunRecord {
  return {
    id: "run-1",
    project: "proj-1",
    status: "succeeded",
    kind: "image",
    model: "google/nano-banana-pro",
    engine: "studio-media-nano-banana-pro",
    created: "2026-08-20T00:00:00Z",
    outputs: [],
    scenes: [],
    bindings: {},
    sends: [],
    characters: ["char-1"],
    plan: null,
    payload: { prompt: null, request: null, response: null },
    ...over,
  } as RunRecord;
}

describe("the body a re-run sends", () => {
  it("strips each send to the three fields that were authored", () => {
    const body = rerunBodyOf(
      record({
        sends: [
          send(),
          send({ order: 2, field: "start_image", role: "start", node: "node-2" }),
        ],
      }),
    );

    // Exactly these keys — `source`, `url`, `name`, `size`, `content_type` and
    // `order` are all derived, and the API works every one of them out again.
    expect(body.sends).toEqual([
      { field: "image_input", role: "reference", node: "node-1" },
      { field: "start_image", role: "start", node: "node-2" },
    ]);
  });

  it("keeps the order the model was shown the images in", () => {
    const body = rerunBodyOf(
      record({
        sends: [
          send({ order: 1, node: "node-a" }),
          send({ order: 2, node: "node-b" }),
          send({ order: 3, node: "node-c" }),
        ],
      }),
    );

    expect(body.sends?.map((entry) => entry.node)).toEqual([
      "node-a",
      "node-b",
      "node-c",
    ]);
  });

  it("copies the plan verbatim, a reconstructed one included", () => {
    const plan = {
      version: 1,
      origin: "backfilled" as const,
      prompt: "a porch at dawn",
      params: { aspect_ratio: "9:16", quality: "high" },
      note: null,
    };
    const body = rerunBodyOf(record({ plan }));

    // `origin` survives: a plan `backfill-plans` rebuilt from a recorded request
    // must not become one a person wrote by being copied.
    expect(body.plan).toEqual(plan);
  });

  it("appends no provenance note — a re-run is the same payload", () => {
    const body = rerunBodyOf(
      record({
        plan: { version: 1, origin: "authored", prompt: "a porch", params: {} },
      }),
    );

    // `note` is inside the digest and the fingerprint. A note here would make
    // every re-run a different submission to the duplicate check.
    expect(body.plan?.note).toBeUndefined();
  });

  it("passes a null plan through rather than inventing one", () => {
    expect(rerunBodyOf(record({ plan: null })).plan).toBeNull();
  });

  it("names the output the same file the source run named", () => {
    const body = rerunBodyOf(record({ output_name: "porch-wide" }));

    expect(body.name).toBe("porch-wide");
  });

  it("leaves the name unset when the source run had none", () => {
    expect(rerunBodyOf(record({ output_name: null })).name).toBeUndefined();
  });

  it("carries the project, kind, model, engine and characters over", () => {
    const body = rerunBodyOf(record({ characters: ["char-1", "char-2"] }));

    expect(body).toMatchObject({
      project: "proj-1",
      kind: "image",
      model: "google/nano-banana-pro",
      engine: "studio-media-nano-banana-pro",
      characters: ["char-1", "char-2"],
    });
  });

  it("falls back to bindings on a run that predates sends", () => {
    const body = rerunBodyOf(
      record({
        sends: [],
        bindings: {
          image_input: [
            { node: "node-1", name: "a.webp", url: "https://example.test/a" },
            { node: "node-2", name: "b.webp", url: "https://example.test/b" },
          ],
          start_image: [
            { node: "node-3", name: "c.webp", url: "https://example.test/c" },
          ],
        },
      }),
    );

    // Node ids, never URLs — hard rule #3, and the API refuses a URL-shaped one.
    expect(body.bindings).toEqual({
      image_input: ["node-1", "node-2"],
      start_image: ["node-3"],
    });
    expect(body.sends).toBeUndefined();
  });

  it("prefers sends when a run carries both", () => {
    const body = rerunBodyOf(
      record({
        sends: [send({ node: "node-1" })],
        // Derived from the sends by the API, so this is the same image twice.
        bindings: {
          image_input: [
            { node: "node-1", name: "front.webp", url: "https://example.test/f" },
          ],
        },
      }),
    );

    expect(body.sends).toEqual([
      { field: "image_input", role: "reference", node: "node-1" },
    ]);
    expect(body.bindings).toBeUndefined();
  });

  it("sends an empty list for a run that binds no images at all", () => {
    const body = rerunBodyOf(record({ sends: [], bindings: {} }));

    expect(body.sends).toEqual([]);
    expect(body.bindings).toBeUndefined();
  });
});
