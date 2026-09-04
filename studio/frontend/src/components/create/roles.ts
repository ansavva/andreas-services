import type { AttachRole, Attachment } from "../../context/CreateBarContext";
import type { ModelEntry, RunKind, RunSendInput } from "../../types";

/**
 * The roles each kind's strip offers, in the order the mockup draws them.
 *
 * Image mode: Reference, Edit. Video mode: Animate (the start frame), End
 * frame, Reference. Nothing about frames on an image run — a still has no
 * start — and `input` on a video would be a second word for its start frame.
 */
export const ROLES_BY_KIND: Record<RunKind, readonly AttachRole[]> = {
  image: ["reference", "input"],
  video: ["start", "end", "reference"],
};

/** What each role is called on the strip, and what it is for. */
export const ROLE_WORDS: Record<AttachRole, { label: string; hint: string }> = {
  reference: {
    label: "Reference",
    hint: "Who and what the render is checked against. Order is send order.",
  },
  input: { label: "Edit", hint: "The image an edit starts from, like “make the coat black”." },
  start: { label: "Animate", hint: "The image the clip starts from." },
  end: { label: "End frame", hint: "How the clip ends." },
};

/**
 * The model input a role binds to, or `null` where this model has no such
 * input — which is when the strip hides the role.
 *
 * Read off the registry entry's `images`, never guessed: the frame-first
 * workflow's whole bargain is that a start frame lands on the field the model
 * calls its start frame. `input` — the image an edit starts from — takes the
 * model's single-image field where it has one (an upscaler's `image`) and its
 * reference list otherwise, since that is the only place an image model
 * without one can be handed a picture.
 */
export function fieldFor(role: AttachRole, entry: ModelEntry | null): string | null {
  const images = entry?.images ?? {};
  switch (role) {
    case "start":
      return images.start ?? null;
    case "end":
      return images.end ?? null;
    case "reference":
      return images.refs ?? null;
    case "input":
      return images.start ?? images.refs ?? null;
  }
}

/**
 * The ordered sends a draft is created with.
 *
 * Attachment order is send order — the strip says so — and an attachment
 * whose role this model has no field for is dropped rather than sent to a
 * field the live schema would refuse. The role travels with the send so the
 * record says what each image was FOR, not only where it went.
 */
export function sendsOf(attachments: readonly Attachment[], entry: ModelEntry | null): RunSendInput[] {
  const sends: RunSendInput[] = [];
  for (const { ref, role } of attachments) {
    const field = fieldFor(role, entry);
    if (field) sends.push({ field, role, node: ref.node });
  }
  return sends;
}

/**
 * Who the run is about, in the order a prompt counts them.
 *
 * The characters whose images are attached come first — those are the ones a
 * `{character.1.profile}` most plausibly means — and the project's own cast
 * follows, so a run with no attachments still binds somebody a template can
 * cite. `{character.N.…}` is positional, which is why this is an ordered list
 * with no duplicates rather than a set.
 */
export function castOf(
  attachments: readonly Attachment[],
  projectCast: ReadonlyArray<{ id: string }>,
): string[] {
  const seen = new Set<string>();
  const cast: string[] = [];
  const add = (id: string | undefined) => {
    if (!id || seen.has(id)) return;
    seen.add(id);
    cast.push(id);
  };
  for (const { ref } of attachments) add(ref.character);
  for (const each of projectCast) add(each.id);
  return cast;
}

/** The first registry entry of a kind, in the order the registry lists them. */
export function defaultEntry(
  models: Record<string, ModelEntry> | null | undefined,
  kind: RunKind,
): ModelEntry | null {
  return Object.values(models ?? {}).find((entry) => entry.kind === kind) ?? null;
}

/** The entry a chosen model names — by Replicate id, registry key or alias. */
export function findEntry(
  models: Record<string, ModelEntry> | null | undefined,
  model: string | null,
): ModelEntry | null {
  if (!model) return null;
  return (
    Object.values(models ?? {}).find(
      (entry) => entry.model === model || entry.key === model || entry.aliases?.includes(model),
    ) ?? null
  );
}
