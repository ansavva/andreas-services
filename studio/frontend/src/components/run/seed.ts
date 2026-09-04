import type { AttachRef, AttachRole, CreateSeed } from "../../context/CreateBarContext";
import type { RunAsset, RunFeedRow, RunSend } from "../../types";

/**
 * A feed row, as something the create bar can start from.
 *
 * **The plan is what a person decided, so it is what Edit loads.** The prompt
 * (a string, or a structured document serialised — the bar shows the tokens,
 * the pipeline decodes nothing), the parameters, the model, the kind, and each
 * send as an attachment carrying its role. A send with no role — a run backfilled
 * from a model the registry does not list — goes in as `reference`, which is
 * the one role every image model has a slot for.
 */
export function seedFromRow(row: RunFeedRow): CreateSeed {
  return {
    project: row.project,
    kind: row.kind,
    model: row.model,
    prompt: promptText(row.plan?.prompt),
    params: { ...(row.plan?.params ?? {}) },
    attachments: row.sends.map((send) => ({
      ref: refOfSend(send),
      role: send.role ?? "reference",
    })),
  };
}

/** The prompt as the bar edits it — prose verbatim, a document serialised. */
export function promptText(prompt: unknown): string | undefined {
  if (prompt == null) return undefined;
  if (typeof prompt === "string") return prompt;
  return JSON.stringify(prompt);
}

/**
 * One output of a run, as an attachment.
 *
 * `output` is 1-based, matching what a runref's `#2` means and what a send's
 * recorded provenance says.
 */
export function refOfOutput(row: { id: string }, asset: RunAsset, index: number): AttachRef {
  return {
    node: asset.node,
    url: asset.url,
    name: asset.name,
    kind: "run",
    run: row.id,
    output: index + 1,
  };
}

/**
 * A send, as an attachment — with the provenance the API recorded, so the bar
 * can say where the picture came from rather than only what it is called.
 */
function refOfSend(send: RunSend): AttachRef {
  const source = send.source ?? { kind: "object" };
  switch (source.kind) {
    case "character":
      return {
        node: send.node,
        url: send.url,
        name: send.name,
        kind: "character",
        ...(source.character ? { character: source.character } : {}),
      };
    case "run":
      return {
        node: send.node,
        url: send.url,
        name: send.name,
        kind: "run",
        ...(source.run ? { run: source.run } : {}),
        ...(source.output ? { output: source.output } : {}),
      };
    case "input-pool":
      return { node: send.node, url: send.url, name: send.name, kind: "input-pool" };
    default:
      return { node: send.node, url: send.url, name: send.name, kind: "object" };
  }
}

/** The seed that runs this row again with one of its outputs attached. */
export function seedWithOutput(
  row: RunFeedRow,
  asset: RunAsset,
  index: number,
  role: AttachRole,
): CreateSeed {
  const seed = seedFromRow(row);
  return {
    ...seed,
    attachments: [...(seed.attachments ?? []), { ref: refOfOutput(row, asset, index), role }],
  };
}
