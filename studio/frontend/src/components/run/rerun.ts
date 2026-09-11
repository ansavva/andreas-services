import type { CreateRunBody, RunAsset, RunFeedRow, RunRecord, RunSend } from "../../types";

/**
 * What a re-run needs to read off a run — the fields the envelope and the
 * feed row share, plus the two only the envelope carries.
 *
 * A feed row is a `RunRecord` projected (`WEB_APP.md`, `?view=feed`): the same
 * plan, the same ordered sends, the same model. What it lacks is `output_name`
 * and the legacy `bindings` map, and both are optional here for that reason —
 * a row re-run keeps the pipeline's default filename, which is what a person
 * pressing Rerun in a feed expects.
 */
export type RerunSource = Pick<RunRecord | RunFeedRow, "project" | "kind" | "model" | "characters" | "plan"> & {
  engine?: string | null;
  output_name?: string | null;
  sends?: RunSend[];
  bindings?: Record<string, RunAsset[]>;
};

/**
 * The body that re-runs a run: the same payload, as a fresh draft.
 *
 * **Byte-identical on purpose, and that is the whole design.** No provenance
 * note is appended and nothing is re-labelled, because `note` is inside the
 * plan and the plan is inside `fingerprint` — so a note saying
 * "re-run of X" would make every re-run a different submission, and the
 * duplicate warning that reads `?fingerprint=` would never fire on the one case
 * it exists for. What distinguishes the attempts is that they are two runs, with
 * two ids and two timestamps, which the catalog already records.
 *
 * `origin` travels verbatim for the same class of reason: a plan `catalog
 * backfill-plans` reconstructed from a recorded request must not silently become
 * one a person wrote. `RunPlanEditor` preserves it through an edit; this
 * preserves it through a copy.
 *
 * Nothing here decides to spend. It builds a draft; the armed gesture that
 * follows is the act, and that is the money.
 */
export function rerunBodyOf(run: RerunSource): CreateRunBody {
  return {
    project: run.project,
    kind: run.kind,
    model: run.model,
    engine: run.engine ?? undefined,
    // The output FILENAME, which lives outside the plan — see `RunRecord`.
    name: run.output_name ?? undefined,
    characters: run.characters,
    plan: run.plan,
    ...imagesOf(run),
  };
}

/**
 * The ordered images, in whichever shape this run can supply.
 *
 * A send read back carries `source`, `url`, `name`, `size` and `order` on top of
 * the three fields it was authored with; all of that is derived — the API
 * re-derives `source` from where the node sits, and re-signs the URL — so
 * sending it back would be asserting a provenance this app did not work out.
 * The three that remain are exactly what the fingerprint hashes.
 *
 * A run that predates sends has only `bindings`, and the fallback emits that map
 * instead: the API reads it through `sends_from_bindings`, with the role left
 * null because the map never carried one. Guessing a role from a field name here
 * would be a second copy of the registry.
 */
function imagesOf(run: RerunSource): Pick<CreateRunBody, "sends" | "bindings"> {
  if (run.sends?.length) {
    return {
      sends: run.sends.map(({ field, role, node }) => ({ field, role, node })),
    };
  }
  const bindings = Object.entries(run.bindings ?? {});
  if (!bindings.length) return { sends: [] };
  return {
    bindings: Object.fromEntries(
      bindings.map(([field, assets]) => [
        field,
        assets.map((asset) => asset.node),
      ]),
    ),
  };
}
