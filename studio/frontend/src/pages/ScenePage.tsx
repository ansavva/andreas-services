import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Alert,
  Badge,
  Button,
  Drawer,
  Field,
  Input,
  Spinner,
  Text,
} from "@ansavva/design-system";

import { getScene, patchShot } from "../apis/studio";
import { AutoTextarea } from "../components/common/AutoTextarea";
import { PageBar } from "../components/layout/PageBar";
import { MediaThumb } from "../components/media/MediaThumb";
import { useResource } from "../hooks/useResource";
import type { Motion, MotionPrompt, Panel, PanelRole, RunAsset, Shot } from "../types";
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
  // One viewer for the whole board rather than one per tile: a scene holds
  // twenty-odd frames and twenty mounted drawers is twenty portals.
  const [viewing, setViewing] = useState<RunAsset | null>(null);

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
      <>
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading scene" />
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Alert.Root intent="danger">
          <Alert.Title>Could not open this scene</Alert.Title>
          <Alert.Description>{error ?? "It may have been deleted."}</Alert.Description>
        </Alert.Root>
      </>
    );
  }

  return (
    <>
      <PageBar crumbs={[{ label: "Project", to: projectPath(data.project) }]}>
        <Text variant="display">{data.title || data.slug}</Text>
        <Badge intent="neutral">{data.status}</Badge>
        <Text variant="caption" tone="muted">
          {formatDate(data.created)}
        </Text>
      </PageBar>

      {data.output && (
        <section className="flex flex-col gap-2">
          <Text variant="title">The cut</Text>
          <button
            type="button"
            onClick={() => navigate(objectPath(data.output!.node))}
            className="w-full max-w-md overflow-hidden rounded-md border border-line bg-card
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <MediaThumb
              nodeId={data.output.node}
              url={data.output.url}
              name={data.output.name}
              isVideo
              aspect="video"
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
          <Badge intent="neutral">{isBracketed(data.shots) ? "bracketed" : "chained"}</Badge>
          <Text variant="caption" tone="muted">
            {data.shots.length} shot{data.shots.length === 1 ? "" : "s"}
            {plannedRuntime(data.shots) ? ` · ${plannedRuntime(data.shots)}s planned` : ""}
            {isBracketed(data.shots)
              ? " · each shot pinned at both ends"
              : " · each shot opens on the last frame of the one before"}
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
                  bracketed={isBracketed(data.shots)}
                  onOpenRun={(run) => navigate(runPath(data.project, run))}
                  onView={setViewing}
                  onSave={saveShot}
                />
              ))}
          </div>
        )}
      </section>

      <FrameViewer asset={viewing} onClose={() => setViewing(null)} />
    </>
  );
}

/**
 * One frame, big.
 *
 * A storyboard tile is 80px because a shot has several and a scene has seven of
 * them; judging whether a pose is right needs the picture at a size you can
 * actually read. Opening the node page would work and loses your place on the
 * board — a drawer keeps the board underneath.
 */
function FrameViewer({ asset, onClose }: { asset: RunAsset | null; onClose: () => void }) {
  const isVideo = (asset?.content_type ?? "").startsWith("video/");
  return (
    <Drawer.Root
      open={asset !== null}
      onOpenChange={(open: boolean) => {
        if (!open) onClose();
      }}
      side="right"
    >
      <Drawer.Backdrop />
      <Drawer.Panel className="flex w-full max-w-2xl flex-col gap-3 p-4">
        <Drawer.Title>{asset?.name ?? "Frame"}</Drawer.Title>
        {asset?.url &&
          (isVideo ? (
            <video src={asset.url} controls playsInline className="max-h-[75vh] w-full object-contain" />
          ) : (
            <img src={asset.url} alt="" className="max-h-[75vh] w-full object-contain" />
          ))}
        <div className="flex flex-wrap gap-2">
          <Drawer.Close>Close</Drawer.Close>
        </div>
      </Drawer.Panel>
    </Drawer.Root>
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
  bracketed,
  onOpenRun,
  onView,
  onSave,
}: {
  shot: Shot;
  n: number;
  bracketed: boolean;
  onOpenRun: (run: string) => void;
  onView: (asset: RunAsset) => void;
  onSave: (shotId: string, body: Partial<Shot>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(() => draftOf(shot));

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

      {/* The clip is OUTPUT and sits on its own; everything else a shot has is
          an INPUT, and `Sends` groups those by what they are sent as. The two
          used to be one filmstrip, which drew the same panel twice — once as a
          tile and once as the reference it becomes. */}
      {shot.clip && (
        <div className="flex flex-wrap gap-2">
          <Frame label="clip" asset={shot.clip} onOpen={onView} />
        </div>
      )}

      {(shot.panels ?? []).length === 0 && !shot.clip && !shot.opens_on?.node && (
        <Text variant="caption" tone="muted">
          No panels — this shot was added straight from a run.
        </Text>
      )}

      <Sends shot={shot} bracketed={bracketed} onView={onView} />

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
 * What this shot intends to send, and what it deliberately does not.
 *
 * **The plan's declaration, not the resolved payload.** Which images actually
 * reach the engine is decided by the submit path against that engine's own rules
 * — Kling counts the start frame toward its cap of 7 and drops every reference
 * the moment an end frame joins them, Seedance excludes references from a start
 * frame outright — and those rules live in one place on purpose. This draws what
 * the storyboard asked for and names the command that resolves it, rather than
 * reimplementing the arithmetic and drifting from it.
 *
 * The distinction it exists to make visible: **a panel's references steer the
 * STILL, and are not what the video engine receives.** Those are two lists and
 * they were both invisible, which is how "why aren't you showing me the images
 * you intend to send" became a fair question.
 */
function Sends({
  shot,
  bracketed,
  onView,
}: {
  shot: Shot;
  bracketed: boolean;
  onView: (asset: RunAsset) => void;
}) {
  const panels = shot.panels ?? [];
  const withRole = (role: PanelRole) => panels.filter((p) => p.role === role);
  const handoff = shot.continues !== false && shot.opens_on?.node ? shot.opens_on : null;
  const startPanel = withRole("start")[0];
  const endPanel = withRole("end")[0];
  // A handoff outranks a start panel and demotes it to a reference — the only
  // frame that makes a cut seamless is the literal last frame of the shot before.
  const demoted = handoff && startPanel ? [startPanel] : [];
  const references = [...demoted, ...withRole("reference")];
  const samples = withRole("sample");
  const plates = shot.motion?.reference_assets ?? [];

  return (
    <section className="flex flex-col gap-3 rounded-md border border-line p-2">
      <SendRow label="Start">
        {handoff?.frame ? (
          <Frame hint="handoff" asset={handoff.frame} onOpen={onView} />
        ) : startPanel ? (
          <Frame
            hint={panelHint(startPanel, false)}
            title={startPanel.prompt}
            asset={startPanel.image}
            onOpen={onView}
          />
        ) : (
          <Slot note="awaits previous shot" />
        )}
      </SendRow>

      {/* **Only when the scene brackets its shots.** A chained scene has no end
          frames anywhere, so a row saying "none" on all seven cards is seven
          rows of nothing. The mode is stated once, at the top of the board. */}
      {bracketed && (
        <SendRow label="End">
          {endPanel ? (
            <Frame
              hint={panelHint(endPanel, false)}
              title={endPanel.prompt}
              asset={endPanel.image}
              onOpen={onView}
            />
          ) : (
            <Slot note="not bracketed" />
          )}
        </SendRow>
      )}

      <SendRow label="References">
        {references.map((p) => (
          <Frame
            key={`p${p.n}`}
            hint={panelHint(p, demoted.includes(p))}
            title={p.prompt}
            asset={p.image}
            onOpen={onView}
          />
        ))}
        {plates.map((a) => (
          <Frame key={a.node} hint="plate" title={a.name} asset={a} onOpen={onView} />
        ))}
        {references.length === 0 && plates.length === 0 && <Slot note="scene frames" />}
      </SendRow>

      {samples.length > 0 && (
        <SendRow label="Samples">
          {samples.map((p) => (
            <Frame
              key={`s${p.n}`}
              hint="not sent"
              title={p.prompt}
              asset={p.image}
              onOpen={onView}
            />
          ))}
        </SendRow>
      )}
    </section>
  );
}

/**
 * Whether a scene pins its shots at both ends.
 *
 * Chained is the default and the common case: one seed, every later shot opening
 * on the previous shot's last frame. Bracketed shots carry an `end` panel. The
 * board states which it is once rather than printing "not bracketed" on every
 * card of a scene that was never going to be.
 */
function isBracketed(shots: Shot[]): boolean {
  return shots.some((s) => (s.panels ?? []).some((p) => p.role === "end"));
}

/**
 * An empty slot — a frame that is planned and not here.
 *
 * **Drawn, not described.** A storyboard is read by looking, so an absent frame
 * is a dashed rectangle the same size as a real one, not a sentence floating
 * where a picture should be. Two or three words inside it say why it is empty.
 */
function Slot({ note }: { note: string }) {
  return (
    <span
      className="flex aspect-[3/4] w-20 shrink-0 items-center justify-center rounded-md
                 border border-dashed border-line bg-surface-alt p-1 text-center"
    >
      <Text variant="caption" tone="muted">
        {note}
      </Text>
    </span>
  );
}

/**
 * The one thing most worth saying about a panel, in priority order.
 *
 * `stale` outranks the rest because it is the only one that means the picture is
 * WRONG — the prompt moved on after the image was rendered, so what you are
 * looking at no longer illustrates the words beside it. Demotion and absence are
 * both ordinary states of a board.
 */
function panelHint(panel: Panel, demoted: boolean): string | undefined {
  if (panel.stale) return "stale";
  if (demoted) return "demoted";
  if (!panel.image) return "not rendered";
  return undefined;
}

function SendRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <Text variant="caption" tone="muted">
        {label}
      </Text>
      <div className="flex flex-wrap items-start gap-2">{children}</div>
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
  /** Omitted inside a `SendRow`, whose own label already says what this is. */
  label?: string;
  hint?: string;
  title?: string;
  asset?: RunAsset;
  /** Opens the frame in the board's viewer. The asset, not its id — the tile
      already holds everything the drawer needs to draw it. */
  onOpen: (asset: RunAsset) => void;
}) {
  const isVideo = (asset?.content_type ?? "").startsWith("video/");

  const shell = asset?.url ? (
    <MediaThumb
      nodeId={asset.node}
      url={asset.url}
      name={asset.name}
      isVideo={isVideo}
      aspect="portrait"
      className="w-24 rounded-md border border-line"
    />
  ) : (
    // A planned-but-unrendered panel is the normal state of a board, not an
    // error, so it draws as a dashed frame carrying its prompt.
    <span
      className="flex aspect-[3/4] w-24 items-center justify-center overflow-hidden rounded-md
                 border border-dashed border-line bg-surface-alt p-1 text-center"
    >
      <Text variant="caption" tone="muted" className="line-clamp-4">
        {title || "not rendered"}
      </Text>
    </span>
  );

  return (
    <span className="flex w-24 flex-col gap-1">
      {asset?.url ? (
        <button
          type="button"
          onClick={() => onOpen(asset)}
          title={title ?? asset.name}
          className="text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {shell}
        </button>
      ) : (
        <span title={title}>{shell}</span>
      )}
      {(label || hint) && (
        <span className="flex flex-wrap items-center gap-1">
          {label && (
            <Text variant="caption" tone="muted">
              {label}
            </Text>
          )}
          {hint && <Badge intent={hint === "stale" ? "warning" : "neutral"}>{hint}</Badge>}
        </span>
      )}
    </span>
  );
}

