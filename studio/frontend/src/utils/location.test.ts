import { describe, expect, it } from "vitest";

import { folderPath, legacyPath, objectPath, targetFromPath } from "./location";

const NODE = "0f2a1c9e-4b7d-4c11-9a3e-2d5b6f8c0a41";

describe("id URLs round-trip", () => {
  it("maps a folder and an object to their own routes", () => {
    expect(folderPath(NODE)).toBe(`/f/${NODE}`);
    expect(objectPath(NODE)).toBe(`/o/${NODE}`);
    expect(targetFromPath(folderPath(NODE))).toEqual({ kind: "folder", id: NODE });
    expect(targetFromPath(objectPath(NODE))).toEqual({ kind: "object", id: NODE });
  });

  it("addresses the library root as `/`, which needs no id", () => {
    expect(folderPath(null)).toBe("/");
    expect(targetFromPath("/")).toEqual({ kind: "folder", id: null });
  });

  it("lands a hand-edited URL on the root rather than throwing", () => {
    expect(targetFromPath("/f")).toEqual({ kind: "folder", id: null });
    expect(targetFromPath(`/f/${NODE}/extra`)).toEqual({ kind: "folder", id: null });
  });
});

describe("legacyPath", () => {
  it("decodes each segment, so spaces and # in real filenames survive", () => {
    // Both appear in this library, and encoding the whole path instead of its
    // segments is what used to eat the separators.
    expect(legacyPath("/projects/a%20b/output/clip%20%232.mp4")).toBe(
      "projects/a b/output/clip #2.mp4",
    );
  });

  it("drops the trailing slash that used to mean `folder`", () => {
    // `/api/resolve` returns the node's `kind`, so the slash is not read any
    // more — a link that lost it in a chat client still lands on the right page.
    expect(legacyPath("/projects/a/runs/")).toBe("projects/a/runs");
    expect(legacyPath("/")).toBe("");
  });

  it("passes a stray % through instead of throwing on the way to a render", () => {
    expect(legacyPath("/projects/100%")).toBe("projects/100%");
  });
});
