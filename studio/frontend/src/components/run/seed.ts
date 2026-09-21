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
 *
 * **A LoRA send is left behind.** The bar has no tile for weights — a LoRA
 * binds from the CLI (`--lora-high-key`) — so an edit of a LoRA run reloads
 * its frame, prompt and params and not the adapters; the run page still
 * shows them, and `lora_scale` rides along in the params.
 *
 * **Whether the seed EDITS the row or COPIES it is decided here, by status.**
 * A run that has not gone out is still a draft: the bar opens that run and
 * writes back to it. One that has is what was sent, and the API refuses to
 * rewrite it, so the bar gets a copy and makes a new draft. `discarded` is
 * unsubmitted too — a save turns it back into a `draft`, which is the API's
 * rule — so it edits in place as well.
 */
export function seedFromRow(row: RunFeedRow): CreateSeed {
  return {
    project: row.project,
    kind: row.kind,
    model: row.model,
    prompt: promptText(row.plan?.prompt),
    params: { ...(row.plan?.params ?? {}) },
    attachments: row.sends.flatMap((send) =>
      send.role === "lora"
        ? []
        : [{ ref: refOfSend(send), role: (send.role ?? "reference") as AttachRole }],
    ),
    ...(isUnsubmitted(row)
      ? {
          editing: {
            run: row.id,
            project: row.project,
            kind: row.kind,
            model: row.model,
            plan: row.plan,
          },
        }
      : {}),
  };
}

/** Whether the run can still be rewritten — the API's `UNSUBMITTED_RUN_STATUSES`. */
export function isUnsubmitted(row: { status: string }): boolean {
  return row.status === "draft" || row.status === "discarded";
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
    case "location":
      return {
        node: send.node,
        url: send.url,
        name: send.name,
        kind: "location",
        ...(source.location ? { location: source.location } : {}),
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
