import { describe, expect, it } from "vitest";

import { sceneAssets } from "./useViewerFeed";
import type { RunAsset, SceneCut, SceneRecord } from "../types";

function asset(node: string): RunAsset {
  return { node, name: `${node}.mp4`, url: `https://signed/${node}`, content_type: "video/mp4" };
}

function cut(id: string, output: RunAsset | null): SceneCut {
  return { id, project: "proj-1", status: "succeeded", kind: "video", model: "m",
           created: "2026-09-01T00:00:00Z", scene: "scene-1", output, thumb: output };
}

function scene(over: Partial<SceneRecord> = {}): SceneRecord {
  return { id: "scene-1", project: "proj-1", name: "s", status: "planned",
           created: "2026-09-01T00:00:00Z", folder: "node-f", runs: [], frames: [],
           output: null, movies: [], ...over };
}

describe("sceneAssets", () => {
  it("leads with the take, then earlier takes, then the cut, then the frames", () => {
    const record = scene({
      output: asset("node-take"),
      cuts: [asset("node-earlier")],
      runs: [cut("run-1", asset("node-clip-1")), cut("run-2", null), cut("run-3", asset("node-clip-3"))],
      frames: [asset("node-seed"), asset("node-handoff")],
    });
    expect(sceneAssets(record).map((a) => a.node)).toEqual([
      "node-take", "node-earlier", "node-clip-1", "node-clip-3", "node-seed", "node-handoff",
    ]);
  });

  it("skips a run in the cut that has not rendered", () => {
    expect(sceneAssets(scene({ runs: [cut("run-1", null)] }))).toEqual([]);
  });
});
