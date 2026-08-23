import { describe, expect, it } from "vitest";

import {
  characterPath,
  folderPath,
  moviePath,
  objectPath,
  projectPath,
  runPath,
  scenePath,
  targetFromPath,
} from "./location";

const NODE = "node-0f2a1c9e-4b7d-4c11-9a3e-2d5b6f8c0a41";

describe("id URLs round-trip", () => {
  it("maps a folder and an object to their own routes", () => {
    expect(folderPath(NODE)).toBe(`/f/${NODE}`);
    expect(objectPath(NODE)).toBe(`/o/${NODE}`);
    expect(targetFromPath(folderPath(NODE))).toEqual({ kind: "folder", id: NODE });
    expect(targetFromPath(objectPath(NODE))).toEqual({ kind: "object", id: NODE });
  });

  it("addresses the library root as `/f`, which needs no id", () => {
    expect(folderPath(null)).toBe("/f");
    expect(targetFromPath("/f")).toEqual({ kind: "folder", id: null });
  });

  it("lands a hand-edited URL on the root rather than throwing", () => {
    // Home is `/` now, so the browser reading it as the library root is what
    // keeps an unrecognised address from reaching a listing with no folder.
    expect(targetFromPath("/")).toEqual({ kind: "folder", id: null });
    expect(targetFromPath(`/f/${NODE}/extra`)).toEqual({ kind: "folder", id: null });
  });
});

describe("entity URLs carry ids, so they survive a rename", () => {
  it("addresses each entity by its own id", () => {
    expect(characterPath("char-1")).toBe("/c/char-1");
    expect(projectPath("proj-1")).toBe("/p/proj-1");
    expect(scenePath("scene-1")).toBe("/s/scene-1");
    expect(moviePath("movie-1")).toBe("/m/movie-1");
  });

  it("nests a run under the project that owns it", () => {
    // The run id alone would fetch it; the project in the path is what lets the
    // page draw a breadcrumb before any request comes back.
    expect(runPath("proj-1", "run-1")).toBe("/p/proj-1/r/run-1");
  });
});
