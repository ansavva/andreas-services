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
  const raw = row.plan?.params?.aspect_ratio;
  if (typeof raw === "string") {
    const match = /^(\d+(?:\.\d+)?)\s*[:x/]\s*(\d+(?:\.\d+)?)$/.exec(raw.trim());
    if (match) {
      const [, w, h] = match;
      if (Number(w) > 0 && Number(h) > 0) return `${w} / ${h}`;
    }
  }
  return row.kind === "video" ? "16 / 9" : "3 / 4";
}
