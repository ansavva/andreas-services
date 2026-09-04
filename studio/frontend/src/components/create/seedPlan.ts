import type { ModelEntry, RunPlan, SnapshotProp } from "../../types";

/** A value a param can hold on its own. Anything else came from a list or a map. */
function isScalar(value: unknown): value is string | number | boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

/**
 * The plan a fresh run starts with: the model's own defaults, and nothing else.
 *
 * **Three kinds of key are dropped, for three different reasons.** `refreshed`
 * is when the snapshot was taken — metadata sitting among the props, which is
 * why anything walking a snapshot has to skip it by name. `prompt` is carried
 * beside the params rather than inside them, and a copy in both would be two
 * answers to what the model is being asked. The entry's image fields are
 * **sends**, never params: an image reaches a provider as a presigned URL minted
 * from a node id (hard rule #3), so a params row naming one would be a second,
 * unchecked path to the same field.
 *
 * Non-scalar defaults go too. Every one of them in the registry today is `[]` —
 * an empty list standing in for "no images yet" — and seeding it would write an
 * empty array into a payload that the send rows are what fill.
 *
 * Lived beside the old new-run strip; the create bar is what seeds from it now.
 */
export function seedPlan(entry: ModelEntry): RunPlan {
  const images = entry.images ?? {};
  const skip = new Set(
    ["refreshed", "prompt", images.refs, images.start, images.end].filter(
      (key): key is string => typeof key === "string",
    ),
  );

  const params: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(entry.snapshot ?? {})) {
    if (skip.has(key)) continue;
    // `refreshed` is a bare string; every real prop is an object. Guarding on
    // the shape as well as the name keeps a future sibling key out too.
    if (!prop || typeof prop !== "object") continue;
    const value = (prop as SnapshotProp).default;
    if (isScalar(value)) params[key] = value;
  }

  return { version: 1, origin: "authored", prompt: "", params };
}
