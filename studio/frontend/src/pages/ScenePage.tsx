import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Alert, Badge, Button, Field, Input, Spinner, Text } from "@ansavva/design-system";

import { getScene, patchShot } from "../apis/studio";
import { AppHeader } from "../components/common/AppHeader";
import { AutoTextarea } from "../components/common/AutoTextarea";
import { useResource } from "../hooks/useResource";
import type { Motion, MotionPrompt, RunAsset, Shot } from "../types";
import { formatDate } from "../utils/format";
import { objectPath, projectPath, runPath } from "../utils/location";

/**
 * One scene: the plan, the shots, and the take they were stitched into.
 *
 * A scene exists because models have a duration ceiling — it is shots joined
 * into one continuous take — so what this page has to show is the *plan* beside
 * what has actually been rendered against it. Each shot names the run that
 * rendered it, by id, which is why revising a plan does not strand the work
 * already done: a shot whose `run` still points somewhere is still rendered, no
 * matter what happened to the plan around it.
 *
 * **The stitching itself is not here and never will be.** `ffmpeg` ships in the
 * pipeline wheel and the Lambda has none: `assemble` downloads, stitches locally,
 * uploads the result and patches the record. The API owns the record, not the
 * encode.
 */
export function ScenePage() {
  const { sceneId = "" } = useParams();
  const navigate = useNavigate();

  const load = useCallback(() => getScene(sceneId), [sceneId]);
  const { data, loading, error, setData } = useResource(load);

  // The route answers with the merged shot, so the page swaps that one row in
  // rather than refetching the scene — a re-GET would re-sign every panel URL
  // on the board to show one reworded sentence.
  const saveShot = useCallback(
    async (shotId: string, body: Partial<Shot>) => {
      const updated = await patchShot(sceneId, shotId, body);
      setData((current) =>
        current
          ? {
              ...current,
              shots: current.shots.map((s) =>
                s.id === shotId ? { ...s, ...updated } : s,
              ),
            }
          : current,
      );
    },
    [sceneId, setData],
  );

  if (loading) {
    return (
      <Shell>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading scene" />
        </div>
      </Shell>
    );
  }

  if (error || !data) {
    return (
      <Shell>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this scene</Alert.Title>
          <Alert.Description>{error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
      </Shell>
    );
  }

  return (
    <Shell subtitle={data.slug}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button intent="ghost" size="sm" onClick={() => navigate(projectPath(data.project))}>
          <span aria-hidden="true">←</span> Project
        </Button>
        <Text variant="display">{data.title || data.slug}</Text>
        <Badge intent="neutral">{data.status}</Badge>
        <Text variant="caption" tone="muted">
          {formatDate(data.created)}
        </Text>
      </div>

      {data.output && (
        <section className="flex flex-col gap-2">
          <Text variant="title">The cut</Text>
          <button
            type="button"
            onClick={() => navigate(objectPath(data.output!.node))}
            className="w-full max-w-md overflow-hidden rounded-md border border-line bg-card
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <video
              src={data.output.url}
              muted
              playsInline
              preload="metadata"
              className="aspect-video w-full object-cover"
            />
            <Text variant="caption" tone="muted" className="truncate px-2 py-1">
              {data.output.name}
            </Text>
          </button>
        </section>
      )}

      {data.setting && (
        <section className="flex flex-col gap-1">
          <Text variant="title">Setting</Text>
          {/* Prepended byte-identically to every panel prompt, which is what
              makes seven separately rendered panels agree on one room. Shown
              once here for the same reason it is written once there. */}
          <Text variant="body" tone="muted" className="max-w-prose">
            {data.setting}
          </Text>
        </section>
      )}

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Text variant="title">Storyboard</Text>
          <Text variant="caption" tone="muted">
            {data.shots.length} shot{data.shots.length === 1 ? "" : "s"}
            {plannedRuntime(data.shots) ? ` · ${plannedRuntime(data.shots)}s planned` : ""}
          </Text>
        </div>
        {data.shots.length === 0 ? (
          <Text variant="body" tone="muted">
            Nothing planned yet.
          </Text>
        ) : (
          <div className="flex flex-col gap-3">
            {[...data.shots]
              .sort((a, b) => a.order - b.order)
              .map((shot, index) => (
                <ShotCard
                  key={shot.id}
                  shot={shot}
                  n={index + 1}
                  onOpenRun={(run) => navigate(runPath(data.project, run))}
                  onOpenNode={(node) => navigate(objectPath(node))}
                  onSave={saveShot}
                />
              ))}
          </div>
        )}
      </section>
    </Shell>
  );
}

/** The planned runtime, which is what a scene will cost time-wise once shot. */
function plannedRuntime(shots: Shot[]): number {
  return shots.reduce((total, shot) => total + (shot.motion?.duration ?? shot.duration ?? 0), 0);
}

/**
 * One shot: what it is, the frames it is made of, and what it rendered into.
 *
 * The layout carries two axes on purpose — the cards run down the page in cut
 * order, and each card's filmstrip runs across it in the order the images reach
 * the model: the frame it opens on, then its panels, then the clip that came
 * out. A storyboard read as a list of prompts is what this page used to be, and
 * a list of prompts is the one thing a person cannot judge a shot from.
 */
function ShotCard({
  shot,
  n,
  onOpenRun,
  onOpenNode,
  onSave,
}: {
  shot: Shot;
  n: number;
  onOpenRun: (run: string) => void;
  onOpenNode: (node: string) => void;
  onSave: (shotId: string, body: Partial<Shot>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(() => draftOf(shot));

  const panels = shot.panels ?? [];
  const motion = shot.motion;
  const caption = shot.beat || shot.prompt || shot.id;
  const duration = motion?.duration ?? shot.duration;

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      // The edited fields go back out as BOTH halves: `prompt_json` is the
      // document, `prompt` is that document serialized, and `prompt` is what the
      // model is actually given. Re-serialized from the parse rather than
      // hand-built, so every key the plan carried — including ones this form
      // does not show — survives the round trip in its original order.
      await onSave(shot.id, draftToShot(shot, draft));
      setEditing(false);
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="flex flex-col gap-3 rounded-md border border-line bg-card p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text variant="body" tone="muted" className="tabular-nums">
          {String(n).padStart(2, "0")}
        </Text>
        <Text variant="body" className="min-w-48 flex-1 font-medium">
          {caption}
        </Text>
        {shot.status && (
          <Badge intent={shot.status === "rendered" ? "success" : "neutral"}>{shot.status}</Badge>
        )}
        {duration ? <Badge intent="neutral">{duration}s</Badge> : null}
        {motion?.model && <Badge intent="neutral">{motion.model}</Badge>}
        {/* One answer to "has this been shot", not two. `status` is computed
            from the plan and is what a storyboarded scene carries; the badge
            below is for a scene assembled from bare runs, which has no status
            at all. Showing both put `rendered` next to `not rendered` on the
            same card. */}
        {shot.run ? (
          <Button intent="ghost" size="sm" onClick={() => onOpenRun(shot.run as string)}>
            Open its run
          </Button>
        ) : (
          !shot.status && <Badge intent="warning">not rendered</Badge>
        )}
        {!editing && (
          <Button
            intent="ghost"
            size="sm"
            onClick={() => {
              setDraft(draftOf(shot));
              setSaveError(null);
              setEditing(true);
            }}
          >
            Edit
          </Button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {/* The frame this shot opens on. It outranks any panel composed for the
            same moment, so it leads the strip — a cut is only seamless from the
            literal last frame of the shot before it. */}
        {shot.opens_on?.frame && (
          <Frame
            label="opens on"
            hint={shot.continues === false ? "kept its own panel" : "handoff"}
            asset={shot.opens_on.frame}
            onOpen={onOpenNode}
          />
        )}

        {panels.length === 0 && !shot.clip && (
          <Text variant="caption" tone="muted">
            No panels — this shot was added straight from a run.
          </Text>
        )}

        {panels.map((panel) => (
          <Frame
            key={panel.n}
            label={panel.role ?? `panel ${panel.n}`}
            hint={panel.stale ? "stale" : undefined}
            title={panel.prompt}
            asset={panel.image}
            onOpen={onOpenNode}
          />
        ))}

        {shot.clip && <Frame label="clip" asset={shot.clip} onOpen={onOpenNode} />}
      </div>

      {motion?.prompt &&
        (editing ? (
          <MotionEditor
            draft={draft}
            onChange={setDraft}
            onSave={save}
            onCancel={() => setEditing(false)}
            saving={saving}
            error={saveError}
          />
        ) : (
          <MotionFields motion={motion} />
        ))}
    </article>
  );
}


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
function parsePrompt(text: string | undefined | null): MotionPrompt | null {
  if (!text) return null;
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed as MotionPrompt;
  } catch {
    return null;
  }
}

/** The blocks worth their own heading, in the order the compiler emits them. */
const PROMPT_FIELDS: Array<{ key: keyof MotionPrompt & string; label: string }> = [
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
  return [camera.shot, camera.movement, camera.lens_mm ? `${camera.lens_mm}mm` : null, camera.speed]
    .filter(Boolean)
    .join(" · ");
}

/** The prompt, read as prose. Falls back to the raw text when it is not JSON. */
function MotionFields({ motion }: { motion: Motion }) {
  const doc = parsePrompt(motion.prompt);
  if (!doc) {
    return (
      <div className="flex flex-col gap-1">
        <Text variant="caption" tone="muted">
          Motion prompt
        </Text>
        <pre className="max-h-56 overflow-auto rounded-md bg-surface-alt p-2 text-xs whitespace-pre-wrap text-muted">
          {motion.prompt}
        </pre>
      </div>
    );
  }
  const camera = cameraLine(doc.camera);
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-[7rem_minmax(0,1fr)]">
      {PROMPT_FIELDS.filter((f) => typeof doc[f.key] === "string" && doc[f.key]).map((f) => (
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

/** The editable copy of a shot, flat because a form is flat. */
interface Draft {
  beat: string;
  duration: string;
  fields: Record<string, string>;
  camera: { shot: string; movement: string; lens_mm: string; speed: string };
}

function draftOf(shot: Shot): Draft {
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
function draftToShot(shot: Shot, draft: Draft): Partial<Shot> {
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

function MotionEditor({
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
    <div className="flex flex-col gap-3 rounded-md border border-line bg-surface-alt p-3">
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

      {PROMPT_FIELDS.filter((f) => draft.fields[f.key] !== undefined).map((f) => (
        <Field.Root key={f.key} name={f.key}>
          <Field.Label>{f.label}</Field.Label>
          <AutoTextarea
            value={draft.fields[f.key]}
            onValueChange={(next: string) =>
              set({ fields: { ...draft.fields, [f.key]: next } })
            }
          />
        </Field.Root>
      ))}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(["shot", "movement", "lens_mm", "speed"] as const).map((k) => (
          <Field.Root key={k} name={`camera-${k}`}>
            <Field.Label>{CAMERA_LABELS[k]}</Field.Label>
            <Input
              value={draft.camera[k]}
              onValueChange={(next) => set({ camera: { ...draft.camera, [k]: next } })}
            />
          </Field.Root>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button intent="primary" size="sm" onClick={onSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        <Button intent="ghost" size="sm" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        {/* The wording is what a shot is judged on and what it costs to get
            wrong, so the gate that spends money re-validates it: `studio scenes
            check` runs the real validator — one camera move, no bare "fast",
            the beat budget — before any render. This form does not, and must not
            pretend to. */}
        <Text variant="caption" tone="muted" className="self-center">
          Re-check with <code>studio scenes check</code> before rendering.
        </Text>
      </div>
    </div>
  );
}

/**
 * One tile of a shot's filmstrip — an image, a clip, or the space where one is
 * not yet.
 *
 * **A placeholder is the normal state of a board**, not an error: a panel is
 * planned before it is rendered, and the gap is the thing a person is looking
 * for when they ask what still needs shooting. So an unboarded panel draws as a
 * dashed frame carrying its prompt rather than being hidden.
 */
function Frame({
  label,
  hint,
  title,
  asset,
  onOpen,
}: {
  label: string;
  hint?: string;
  title?: string;
  asset?: RunAsset;
  onOpen: (node: string) => void;
}) {
  const isVideo = (asset?.content_type ?? "").startsWith("video/");
  const body = asset?.url ? (
    isVideo ? (
      <video src={asset.url} muted playsInline preload="metadata" className="h-full w-full object-cover" />
    ) : (
      <img src={asset.url} alt="" className="h-full w-full object-cover" />
    )
  ) : (
    <span className="flex h-full w-full items-center justify-center p-1 text-center">
      <Text variant="caption" tone="muted" className="line-clamp-4">
        {title || "not rendered"}
      </Text>
    </span>
  );

  const shell = (
    <span
      className={`block aspect-[3/4] w-24 overflow-hidden rounded-md bg-surface-alt ${
        asset?.url ? "border border-line" : "border border-dashed border-line"
      }`}
    >
      {body}
    </span>
  );

  return (
    <span className="flex w-24 flex-col gap-1">
      {asset?.node ? (
        <button
          type="button"
          onClick={() => onOpen(asset.node)}
          title={title ?? asset.name}
          className="text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {shell}
        </button>
      ) : (
        <span title={title}>{shell}</span>
      )}
      <span className="flex flex-wrap items-center gap-1">
        <Text variant="caption" tone="muted">
          {label}
        </Text>
        {hint && <Badge intent={hint === "stale" ? "warning" : "neutral"}>{hint}</Badge>}
      </span>
    </span>
  );
}

function Shell({ children, subtitle }: { children: React.ReactNode; subtitle?: string }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <AppHeader subtitle={subtitle ?? "scene"} />
      {children}
    </div>
  );
}
