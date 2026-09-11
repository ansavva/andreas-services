import { describe, expect, it } from "vitest";

import type { RunFeedRow, RunSend } from "../../types";
import { promptText, refOfOutput, seedFromRow, seedWithOutput } from "./seed";

function send(over: Partial<RunSend>): RunSend {
  return {
    node: "node-s1",
    name: "seed-01.jpg",
    url: "https://signed/seed-01.jpg",
    content_type: "image/jpeg",
    order: 1,
    field: "input_images",
    role: "reference",
    source: { kind: "character", character: "char-1", group: "face" },
    ...over,
  };
}

function row(over: Partial<RunFeedRow> = {}): RunFeedRow {
  return {
    id: "run-1",
    lib: "lib-1",
    project: "proj-1",
    status: "succeeded",
    kind: "image",
    engine: "studio-media-gpt-image-2",
    model: "openai/gpt-image-2",
    created: "2026-09-04T10:00:00Z",
    updated: null,
    submitted: "2026-09-04T10:00:05Z",
    completed: "2026-09-04T10:01:00Z",
    error: null,
    cost: null,
    thumb: null,
    plan: {
      version: 1,
      origin: "authored",
      prompt: "a portrait, 85mm",
      params: { aspect_ratio: "3:4", quality: "high" },
    },
    characters: ["char-1"],
    cast: [{ id: "char-1", name: "jason" }],
    sends: [send({})],
    outputs: [
      { node: "node-o1", name: "out-1.png", url: "https://signed/out-1.png", content_type: "image/png" },
    ],
    ...over,
  };
}

describe("seedFromRow", () => {
  it("carries the plan, the model and the kind", () => {
    const seed = seedFromRow(row());
    expect(seed).toMatchObject({
      project: "proj-1",
      kind: "image",
      model: "openai/gpt-image-2",
      prompt: "a portrait, 85mm",
      params: { aspect_ratio: "3:4", quality: "high" },
    });
  });

  it("turns each send into an attachment with its role and provenance", () => {
    const seed = seedFromRow(
      row({
        sends: [
          send({}),
          send({
            node: "node-s2",
            order: 2,
            role: "start",
            source: { kind: "run", run: "run-0", output: 2 },
          }),
          send({ node: "node-s3", order: 3, role: null, source: { kind: "input-pool", position: 1 } }),
        ],
      }),
    );
    expect(seed.attachments).toEqual([
      {
        ref: { node: "node-s1", url: "https://signed/seed-01.jpg", name: "seed-01.jpg", kind: "character", character: "char-1" },
        role: "reference",
      },
      {
        ref: { node: "node-s2", url: "https://signed/seed-01.jpg", name: "seed-01.jpg", kind: "run", run: "run-0", output: 2 },
        role: "start",
      },
      // A send with no recorded role goes in as a reference — the one slot
      // every image model has.
      {
        ref: { node: "node-s3", url: "https://signed/seed-01.jpg", name: "seed-01.jpg", kind: "input-pool" },
        role: "reference",
      },
    ]);
  });

  it("copies the params rather than sharing the row's object", () => {
    const source = row();
    const seed = seedFromRow(source);
    seed.params!.extra = 1;
    expect(source.plan!.params).not.toHaveProperty("extra");
  });

  it("serialises a structured prompt and leaves prose alone", () => {
    expect(promptText("plain words")).toBe("plain words");
    expect(promptText({ shots: [{ camera: "push in" }] })).toBe('{"shots":[{"camera":"push in"}]}');
    expect(promptText(null)).toBeUndefined();
    expect(seedFromRow(row({ plan: null })).prompt).toBeUndefined();
  });
});

describe("seedWithOutput", () => {
  it("adds one output as a 1-based attachment in the role asked for", () => {
    const source = row();
    const seed = seedWithOutput(source, source.outputs[0]!, 0, "start");
    expect(seed.attachments).toHaveLength(2);
    expect(seed.attachments![1]).toEqual({
      ref: { node: "node-o1", url: "https://signed/out-1.png", name: "out-1.png", kind: "run", run: "run-1", output: 1 },
      role: "start",
    });
    expect(refOfOutput(source, source.outputs[0]!, 2).output).toBe(3);
  });
});
