import type { CreateRunBody, RunRecord } from "../../types";

/**
 * The body that re-runs a run: the same payload, as a fresh draft.
 *
 * **Byte-identical on purpose, and that is the whole design.** No provenance
 * note is appended and nothing is re-labelled, because `note` is inside the
 * plan and the plan is inside `plan_digest` and `fingerprint` — so a note saying
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
 * Nothing here decides to spend. It builds a draft; the armed Run gesture on the
 * new run's page is the approval, and the submit after it is the money.
 */
export function rerunBodyOf(run: RunRecord): CreateRunBody {
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
 * The three that remain are exactly what `plan_digest` hashes.
 *
 * A run that predates sends has only `bindings`, and the fallback emits that map
 * instead: the API reads it through `sends_from_bindings`, with the role left
 * null because the map never carried one. Guessing a role from a field name here
 * would be a second copy of the registry.
 */
function imagesOf(run: RunRecord): Pick<CreateRunBody, "sends" | "bindings"> {
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
