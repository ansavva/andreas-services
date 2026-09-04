import { Alert, Button, Field, Input, Text } from "@ansavva/design-system";

import type { Motion, MotionPrompt, Shot } from "../../types";
import { AutoTextarea } from "../common/AutoTextarea";

/**
 * The storyboard, split out of `ScenePage`.
 *
 * The page was 813 lines holding a board, a card, a prompt document, an editor
 * and a filmstrip — five things that change for different reasons. Nothing here
 * changed in the move.
 */

/**
 * The motion prompt as the document it is.
 *
 * **This is studio's own document, and reading it apart is not the thing the run
 * page refuses.** That rule is about `request.json` — the PROVIDER's payload,
 * whose shape studio does not own and must not pick fields out of. This one has
 * a schema `studio prompt` writes and validates, and it reaches the model as a
 * string only because every engine's prompt field is a string. Showing a person
 * 1.4 kB of escaped JSON to read is not showing them the prompt.
 *
 * `null` when it does not parse, which is a legitimate state: a plain prose
 * prompt is valid on every engine here, and the raw text is shown instead.
 */
export function parsePrompt(
  text: string | undefined | null,
): MotionPrompt | null {
  if (!text) return null;
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      return null;
    return parsed as MotionPrompt;
  } catch {
    return null;
  }
}

/** The blocks worth their own heading, in the order the compiler emits them. */
export const PROMPT_FIELDS: Array<{
  key: keyof MotionPrompt & string;
  label: string;
}> = [
  { key: "subject", label: "Subject" },
  { key: "action", label: "Action" },
  { key: "scene", label: "Scene" },
  { key: "lighting", label: "Lighting" },
  { key: "style", label: "Style" },
  { key: "audio", label: "Audio" },
  { key: "avoid", label: "Avoid" },
];

function cameraLine(camera: MotionPrompt["camera"]): string {
  if (!camera) return "";
  return [
    camera.shot,
    camera.movement,
    camera.lens_mm ? `${camera.lens_mm}mm` : null,
    camera.speed,
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * The prompt, read as prose. Falls back to the raw text when it is not JSON.
 *
 * **Takes a prompt rather than a shot, because a run has one too.** A run's
 * plan and a shot's motion carry the same artifact — studio's own compiled
 * document — and the run screen was drawing it as raw JSON while this drew
 * fields. JSON is not what a person reads or edits, so both use this.
 */
export function PromptFields({
  prompt,
}: {
  prompt: string | undefined | null;
}) {
  return <MotionFields motion={{ prompt: prompt ?? "" } as Motion} />;
}

/** The prompt, read as prose. Falls back to the raw text when it is not JSON. */
export function MotionFields({ motion }: { motion: Motion }) {
  const doc = parsePrompt(motion.prompt);
  if (!doc) {
    return (
      <div className="flex flex-col gap-1">
        <Text variant="caption" tone="muted">
          Motion prompt
        </Text>
        <pre className="max-h-56 overflow-auto rounded-none bg-surface-alt p-2 text-xs whitespace-pre-wrap text-muted">
          {motion.prompt}
        </pre>
      </div>
    );
  }
  const camera = cameraLine(doc.camera);
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-[7rem_minmax(0,1fr)]">
      {PROMPT_FIELDS.filter(
        (f) => typeof doc[f.key] === "string" && doc[f.key],
      ).map((f) => (
        <div key={f.key} className="contents">
          <dt>
            <Text variant="caption" tone="muted">
              {f.label}
            </Text>
          </dt>
          <dd className="m-0">
            <Text variant="body" className="max-w-prose">
              {doc[f.key] as string}
            </Text>
          </dd>
        </div>
      ))}
      {camera && (
        <div className="contents">
          <dt>
            <Text variant="caption" tone="muted">
              Camera
            </Text>
          </dt>
          <dd className="m-0">
            <Text variant="body">{camera}</Text>
          </dd>
        </div>
      )}
    </dl>
  );
}

/** The document's string fields, flattened for a form. */
export function fieldsOf(doc: MotionPrompt): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const f of PROMPT_FIELDS) {
    if (typeof doc[f.key] === "string") fields[f.key] = doc[f.key] as string;
  }
  return fields;
}

/**
 * The form's values back into the document.
 *
 * **Rebuilt from the original, never from the form alone**, so a key the form
 * does not show — `dialogue`, whatever the schema grows next — survives an edit
 * in its original position rather than being silently dropped.
 */
export function docWithFields(
  original: MotionPrompt,
  fields: Record<string, string>,
  camera?: { shot: string; movement: string; lens_mm: string; speed: string },
): MotionPrompt {
  const doc: MotionPrompt = { ...original };
  for (const f of PROMPT_FIELDS) {
    const next = fields[f.key];
    if (next === undefined) continue;
    if (next.trim()) doc[f.key] = next;
    else delete doc[f.key];
  }
  if (camera) {
    const lens = Number(camera.lens_mm);
    const built = {
      ...(camera.shot ? { shot: camera.shot } : {}),
      ...(camera.movement ? { movement: camera.movement } : {}),
      ...(camera.lens_mm && Number.isFinite(lens) ? { lens_mm: lens } : {}),
      ...(camera.speed ? { speed: camera.speed } : {}),
    };
    if (Object.keys(built).length) doc.camera = built;
    else delete doc.camera;
  }
  return doc;
}

/** The editable copy of a shot, flat because a form is flat. */
export interface Draft {
  beat: string;
  duration: string;
  fields: Record<string, string>;
  camera: { shot: string; movement: string; lens_mm: string; speed: string };
}

export function draftOf(shot: Shot): Draft {
  const doc = parsePrompt(shot.motion?.prompt) ?? {};
  const fields: Record<string, string> = {};
  for (const f of PROMPT_FIELDS) {
    if (typeof doc[f.key] === "string") fields[f.key] = doc[f.key] as string;
  }
  return {
    beat: shot.beat ?? "",
    duration: String(shot.motion?.duration ?? shot.duration ?? ""),
    fields,
    camera: {
      shot: doc.camera?.shot ?? "",
      movement: doc.camera?.movement ?? "",
      lens_mm: doc.camera?.lens_mm ? String(doc.camera.lens_mm) : "",
      speed: doc.camera?.speed ?? "",
    },
  };
}

/**
 * The draft, back into the shape the shots route takes.
 *
 * **Rebuilt from the parsed original, not from the form alone**, so every key the
 * plan carried that this form does not show — `dialogue`, anything the schema
 * grows next — survives an edit in its original position. A form that rewrote
 * the document from its own fields would silently drop them.
 */
export function draftToShot(shot: Shot, draft: Draft): Partial<Shot> {
  const doc: MotionPrompt = { ...(parsePrompt(shot.motion?.prompt) ?? {}) };
  for (const f of PROMPT_FIELDS) {
    const next = draft.fields[f.key];
    if (next !== undefined) {
      if (next.trim()) doc[f.key] = next;
      else delete doc[f.key];
    }
  }
  const lens = Number(draft.camera.lens_mm);
  const camera = {
    ...(draft.camera.shot ? { shot: draft.camera.shot } : {}),
    ...(draft.camera.movement ? { movement: draft.camera.movement } : {}),
    ...(Number.isFinite(lens) && draft.camera.lens_mm ? { lens_mm: lens } : {}),
    ...(draft.camera.speed ? { speed: draft.camera.speed } : {}),
  };
  if (Object.keys(camera).length) doc.camera = camera;
  else delete doc.camera;

  const duration = Number(draft.duration);
  return {
    beat: draft.beat,
    motion: {
      ...(shot.motion ?? { prompt: "" }),
      prompt: JSON.stringify(doc, null, 2),
      prompt_json: doc,
      ...(draft.duration && Number.isFinite(duration) ? { duration } : {}),
    },
  };
}

const CAMERA_LABELS = {
  shot: "Shot",
  movement: "Movement",
  lens_mm: "Lens (mm)",
  speed: "Speed",
} as const;

export function MotionEditor({
  draft,
  onChange,
  onSave,
  onCancel,
  saving,
  error,
}: {
  draft: Draft;
  onChange: (next: Draft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}) {
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch });
  return (
    <div className="flex flex-col gap-3 rounded-none border border-line bg-surface-alt p-3">
      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not save this shot</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_8rem]">
        <Field.Root name="beat">
          <Field.Label>Beat</Field.Label>
          <Input value={draft.beat} onValueChange={(beat) => set({ beat })} />
        </Field.Root>
        <Field.Root name="duration">
          <Field.Label>Duration (s)</Field.Label>
          <Input
            value={draft.duration}
            inputMode="numeric"
            onValueChange={(duration) => set({ duration })}
          />
        </Field.Root>
      </div>

      {PROMPT_FIELDS.filter((f) => draft.fields[f.key] !== undefined).map(
        (f) => (
          <Field.Root key={f.key} name={f.key}>
            <Field.Label>{f.label}</Field.Label>
            <AutoTextarea
              value={draft.fields[f.key]}
              onValueChange={(next: string) =>
                set({ fields: { ...draft.fields, [f.key]: next } })
              }
            />
          </Field.Root>
        ),
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(["shot", "movement", "lens_mm", "speed"] as const).map((k) => (
          <Field.Root key={k} name={`camera-${k}`}>
            <Field.Label>{CAMERA_LABELS[k]}</Field.Label>
            <Input
              value={draft.camera[k]}
              onValueChange={(next) =>
                set({ camera: { ...draft.camera, [k]: next } })
              }
            />
          </Field.Root>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button intent="primary" size="sm" onClick={onSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        <Button intent="secondary" size="sm" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
