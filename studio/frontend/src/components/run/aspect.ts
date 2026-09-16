import type { RunFeedRow } from "../../types";

/**
 * The shape a run's outputs will have, as a CSS `aspect-ratio` value.
 *
 * **From the plan, not the kind.** A 9:16 clip drawn in a 16:9 box and
 * covered is a torso with no head — which is what the feed did until a
 * portrait video went through it. Every image and video model here takes an
 * `aspect_ratio` of the form `W:H`, so the plan already says what is coming
 * back; the kind's default is only for a plan that does not say (`auto`,
 * `match_input_image`, or a model with no such knob).
 */
export function ratioOf(row: Pick<RunFeedRow, "kind" | "plan">): string {
  // `aspect_ratio` as `W:H` on most models; `size` as `W*H` pixels on the
  // Runpod ones (Wan, Z-Image), which have no aspect field at all. Either
  // says the shape; the first that parses wins.
  for (const raw of [row.plan?.params?.aspect_ratio, row.plan?.params?.size]) {
    if (typeof raw !== "string") continue;
    const match = /^(\d+(?:\.\d+)?)\s*[:x*/]\s*(\d+(?:\.\d+)?)$/.exec(raw.trim());
    if (match) {
      const [, w, h] = match;
      if (Number(w) > 0 && Number(h) > 0) return `${w} / ${h}`;
    }
  }
  return row.kind === "video" ? "16 / 9" : "3 / 4";
}

/**
 * How many tiles a run in flight will fill.
 *
 * Read off the plan's own count parameter, whichever name the model gives it;
 * one otherwise. A guess drawn as placeholders costs nothing if wrong — the
 * real outputs replace them the moment the run lands.
 */
export function expectedOutputs(row: RunFeedRow): number {
  const params = row.plan?.params ?? {};
  for (const key of ["outputs", "num_outputs", "number_of_images", "n"]) {
    const value = params[key];
    if (typeof value === "number" && value >= 1)
      return Math.min(Math.floor(value), 8);
  }
  return 1;
}
