import { expect, it } from "vitest";

import { shotAssets } from "./useViewerFeed";
import type { RunAsset, Shot } from "../types";

/**
 * The feed decides what the viewer can open. Anything the board DRAWS has to be
 * in here, or clicking that tile lands on a node the reel does not hold and
 * reads as a dead link rather than playing.
 */

function asset(node: string): RunAsset {
  return { node, name: `${node}.mp4`, url: `https://x/${node}.mp4` };
}

function shot(over: Partial<Shot> = {}): Shot {
  return { id: "shot-01", order: 10, prompt: "", run: null, panel: null, ...over };
}

it("carries the clip a shot rendered into", () => {
  expect(shotAssets(shot({ clip: asset("node-now") })).map((a) => a.node)).toContain("node-now");
});

it("carries earlier takes as well as the current clip", () => {
  // The bug this file exists for: the card drew a tile per take and the feed
  // held none of them, so every earlier take was a dead link.
  const assets = shotAssets(
    shot({
      clip: asset("node-now"),
      takes: [{ run: "run-old", node: "node-was", clip: asset("node-was") }],
    }),
  );
  expect(assets.map((a) => a.node)).toEqual(["node-now", "node-was"]);
});

it("skips a take whose clip the API could not expand", () => {
  const assets = shotAssets(shot({ takes: [{ run: "run-gone", node: "node-gone" }] }));
  expect(assets).toEqual([]);
});

it("leaves out the handoff of a shot that does not continue", () => {
  // Not part of the fix — asserted because the fix appends to this list and a
  // regression here would be silent.
  const opens_on = { node: "node-h", from_run: "run-prev", frame: asset("node-h") };
  expect(shotAssets(shot({ continues: false, opens_on })).map((a) => a.node)).toEqual([]);
  expect(shotAssets(shot({ continues: true, opens_on })).map((a) => a.node)).toEqual(["node-h"]);
});
