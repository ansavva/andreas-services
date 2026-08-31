import { useCallback, useMemo, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Field,
  Input,
  Select,
  Text,
} from "@ansavva/design-system";

import { getProject, patchRunPlan, patchRunSends } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { FileEntry, RunPlan, RunRecord, RunSend } from "../../types";
import { AutoTextarea } from "../common/AutoTextarea";
import {
  PROMPT_FIELDS,
  docWithFields,
  fieldsOf,
  parsePrompt,
} from "../scene/motionPrompt";
import { TrashIcon } from "../common/icons";
import { MediaPicker } from "../browse/MediaPicker";
import { MediaThumb } from "../media/MediaThumb";

/** What a send may be FOR. The API refuses anything else. */
const ROLES = ["start", "end", "reference", "input"] as const;

/**
 * One row of the sends editor.
 *
 * `name` and `url` are for drawing and are not sent: a send is `field`, `role`
 * and `node`, which is exactly what the digest hashes. A row added in this
 * session has the name and URL the picker gave it and no `order`, because the
 * order is the position in this list and is settled at save.
 */
interface Row {
  /** Stable across a reorder, which a node id is not — the same node can appear twice. */
  key: string;
  field: string;
  role: string;
  node: string;
  name: string;
  url?: string;
  isVideo: boolean;
}

/**
 * Edit an unsubmitted run — the half of the plan that has had routes and no
 * hands since runs gained one.
 *
 * **Everything here withdraws the approval, and that is the API's doing rather
 * than this component's.** `PATCH /plan` and `PATCH /sends` each recompute the
 * digest, clear `approval` and return the run to `draft`. Hard rule #2 says
 * re-approve after *any* edit; this is what makes that mechanical instead of
 * remembered, and the copy below says so before anything is typed rather than
 * after it is saved.
 *
 * **Two routes, so only what moved is written.** Rewording a prompt leaves the
 * send rows alone and reordering the images leaves the plan alone — which
 * matters because each write is a full replace of its half.
 */
export function RunPlanEditor({
  run,
  onSaved,
  onCancel,
}: {
  run: RunRecord;
  /** The updated run, straight off the response — the page swaps it in. */
  onSaved: (updated: RunRecord) => void;
  onCancel: () => void;
}) {
  /**
   * Whether the prompt is a document or a sentence, decided **once** from the
   * run as it arrived.
   *
   * A structured prompt is authored as JSON by `studio prompt` and flattening one
   * into prose would throw away the structure that makes it re-editable, so the
   * two are edited differently: a document is parsed back and must stay valid, a
   * sentence is saved as the string it is. Deciding it from the draft instead —
   * "does this parse as JSON right now" — would change the meaning of the box
   * under the cursor as somebody typed a `{`.
   */
  const structured = useMemo(
    () => run.plan?.prompt != null && typeof run.plan.prompt !== "string",
    [run.plan],
  );

  const [prompt, setPrompt] = useState(() => promptText(run.plan?.prompt));
  /**
   * A structured prompt is edited FIELD BY FIELD, the way a shot's is.
   *
   * It used to be one textarea of raw JSON that had to stay valid — so a
   * misplaced comma lost the save, and reading your own prompt meant reading
   * escaping. The document is studio's own, with a schema `studio prompt`
   * validates, so a form over its fields is both safer and what a person came
   * to change. A prose prompt has no fields and keeps the textarea.
   */
  const [promptFields, setPromptFields] = useState<Record<string, string>>(() =>
    fieldsOf(parsePrompt(promptText(run.plan?.prompt)) ?? {}),
  );
  const [camera, setCamera] = useState(() => {
    const doc = parsePrompt(promptText(run.plan?.prompt)) ?? {};
    return {
      shot: doc.camera?.shot ?? "",
      movement: doc.camera?.movement ?? "",
      lens_mm: doc.camera?.lens_mm ? String(doc.camera.lens_mm) : "",
      speed: doc.camera?.speed ?? "",
    };
  });
  const [note, setNote] = useState(run.plan?.note ?? "");
  const [params, setParams] = useState<[string, string][]>(() =>
    Object.entries(run.plan?.params ?? {}).map(([key, value]) => [
      key,
      paramText(value),
    ]),
  );
  const [rows, setRows] = useState<Row[]>(() => run.sends.map(rowOf));
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const move = useCallback((index: number, by: number) => {
    setRows((current) => {
      const to = index + by;
      const moved = current[index];
      const displaced = current[to];
      if (moved === undefined || displaced === undefined) return current;
      const next = [...current];
      next[index] = displaced;
      next[to] = moved;
      return next;
    });
  }, []);

  const save = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      let latest = run;

      // Parsed before anything is written, so a malformed document cannot leave
      // the plan saved and the images not — or the other way round.
      const nextPrompt = structured
        ? JSON.stringify(
            docWithFields(
              parsePrompt(promptText(run.plan?.prompt)) ?? {},
              promptFields,
              camera,
            ),
          )
        : prompt;
      const plan = planOf(run.plan, nextPrompt, structured, params, note);
      if (JSON.stringify(plan) !== JSON.stringify(run.plan)) {
        latest = await patchRunPlan(run.id, plan);
      }

      const sends = rows.map((row) => ({
        field: row.field,
        role: row.role === "" ? null : row.role,
        node: row.node,
      }));
      if (JSON.stringify(sends) !== JSON.stringify(sentOf(run.sends))) {
        latest = await patchRunSends(run.id, sends);
      }

      onSaved(latest);
    } catch (err) {
      setError(
        err instanceof SyntaxError
          ? `The prompt is not valid JSON: ${err.message}. Nothing was saved.`
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }, [
    camera,
    promptFields,
    note,
    onSaved,
    params,
    prompt,
    rows,
    run,
    structured,
  ]);

  /**
   * Which model inputs this run already binds — the choices offered for a new
   * image, plus free text.
   *
   * **Read off the run rather than off a registry**, because there is no
   * registry here and there must not become one: which fields a model accepts is
   * `models.json`, the pipeline owns it, and a copy in this app would be a second
   * answer that goes stale silently. What the run itself binds is a fact this
   * page already holds, and a wrong field is refused at submit by the live schema
   * check rather than shipped.
   */
  const fields = useMemo(
    () => Array.from(new Set(rows.map((row) => row.field).filter(Boolean))),
    [rows],
  );

  /**
   * The project this run belongs to — read for its root folder, which is where
   * the picker opens.
   *
   * **The same cache key `useProjectCrumb` uses**, so the record is already
   * there by the time anybody presses Add: the crumb above this page asked for
   * it while the run was loading. `null` until it answers, which the picker
   * reads as the library root.
   */
  const { data: project } = useResource(
    run.project ? ["project", run.project] : null,
    useCallback(() => getProject(run.project), [run.project]),
  );

  return (
    <section className="flex flex-col gap-4 rounded-none border border-line bg-card p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text variant="title">Editing the plan</Text>
        <Badge intent="warning">withdraws the approval</Badge>
      </div>

      <Text variant="caption" tone="muted" className="max-w-prose">
        Saving any change here returns this run to a draft and clears who
        approved it. Nothing can be submitted on a yes given to a different
        payload.
      </Text>

      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>That did not save</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {structured ? (
        <>
          {PROMPT_FIELDS.filter((f) => promptFields[f.key] !== undefined).map(
            (f) => (
              <Field.Root key={f.key} name={f.key}>
                <Field.Label>{f.label}</Field.Label>
                <AutoTextarea
                  value={promptFields[f.key]}
                  onValueChange={(next: string) =>
                    setPromptFields({ ...promptFields, [f.key]: next })
                  }
                />
              </Field.Root>
            ),
          )}

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(["shot", "movement", "lens_mm", "speed"] as const).map((k) => (
              <Field.Root key={k} name={`camera_${k}`}>
                <Field.Label>{k === "lens_mm" ? "Lens (mm)" : k}</Field.Label>
                <Input
                  value={camera[k]}
                  onValueChange={(next: string) =>
                    setCamera({ ...camera, [k]: next })
                  }
                />
              </Field.Root>
            ))}
          </div>
        </>
      ) : (
        <Field.Root name="prompt">
          <Field.Label>Prompt</Field.Label>
          <AutoTextarea
            value={prompt}
            onValueChange={setPrompt}
            minRows={4}
            className="font-mono text-xs"
          />
          <Field.Description>
            Saved as the sentence it is. Nothing here parses it.
          </Field.Description>
        </Field.Root>
      )}

      <Params rows={params} onChange={setParams} />

      <Field.Root name="note">
        <Field.Label>Note</Field.Label>
        <Input
          value={note}
          onValueChange={setNote}
          placeholder="What this run is for"
        />
        <Field.Description>
          For a reader. It is part of the plan, so it is part of what an
          approval names.
        </Field.Description>
      </Field.Root>

      <Sends
        rows={rows}
        fields={fields}
        onChange={setRows}
        onMove={move}
        onAdd={() => setPicking(true)}
      />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button intent="ghost" size="sm" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => void save()} disabled={busy}>
          {busy ? "Saving…" : "Save the plan"}
        </Button>
      </div>

      {picking && (
        <MediaPicker
          noun="images to send"
          // **The project, not the run.** A draft's own folder holds an empty
          // `output/` and two payload documents, so opening there put an empty
          // listing in front of every add — measured on the dev stack, not
          // guessed. The project holds the input pool and the earlier runs, and
          // a character's references are a walk up and across.
          startId={project?.root ?? null}
          taken={new Set(rows.map((row) => row.node))}
          onSubmit={async (files) => {
            setRows((current) => [
              ...current,
              ...files.map((file) => added(file, current)),
            ]);
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      )}
    </section>
  );
}

/**
 * The parameters, as rows.
 *
 * **A key-value editor rather than a JSON box**, because the values are a flat
 * map of knobs — aspect ratio, quality, duration — and typing braces around
 * three of them to change one is the kind of edit a text box makes and a form
 * does not.
 */
function Params({
  rows,
  onChange,
}: {
  rows: [string, string][];
  onChange: (next: [string, string][]) => void;
}) {
  const set = (index: number, pair: [string, string]) =>
    onChange(rows.map((row, at) => (at === index ? pair : row)));

  return (
    <div className="flex flex-col gap-2">
      <Text variant="caption" tone="muted">
        Parameters
      </Text>

      {rows.map(([key, value], index) => (
        // Not `flex-wrap`: at 390px a wrapping row put the delete button alone
        // on a line of its own under every parameter, which reads as a control
        // belonging to whatever comes next.
        <div key={index} className="flex items-center gap-2">
          <Input
            aria-label={`Parameter ${index + 1} name`}
            value={key}
            onValueChange={(next: string) => set(index, [next, value])}
            className="w-32 shrink-0 sm:w-40"
          />
          <Input
            aria-label={`Parameter ${index + 1} value`}
            value={value}
            onValueChange={(next: string) => set(index, [key, next])}
            className="min-w-0 flex-1"
          />
          <Button
            intent="ghost"
            size="sm"
            className="shrink-0"
            aria-label={`Remove ${key || `parameter ${index + 1}`}`}
            onClick={() => onChange(rows.filter((_, at) => at !== index))}
          >
            <TrashIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </Button>
        </div>
      ))}

      <div className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2">
        <Button
          intent="ghost"
          size="sm"
          onClick={() => onChange([...rows, ["", ""]])}
        >
          Add a parameter
        </Button>
        {/* Said out loud, because it is the one place this form guesses. A value
            that reads as JSON is stored as JSON — `8` as a number, `true` as a
            boolean — and anything else is stored as the string it looks like,
            which is what `png` and `16:9` are. */}
        <Text variant="caption" tone="muted">
          Numbers and true/false are stored as such; everything else as text.
        </Text>
      </div>
    </div>
  );
}

/**
 * The ordered images, as editable rows.
 *
 * **A list, not the filmstrip the read-only view draws.** The order is the
 * payload — a prompt citing "the first image" is citing this list — so the thing
 * being edited is a sequence, and a sequence with controls on each item is a row
 * per item. The numbers are the same numbers the filmstrip shows.
 */
function Sends({
  rows,
  fields,
  onChange,
  onMove,
  onAdd,
}: {
  rows: Row[];
  fields: string[];
  onChange: (next: Row[]) => void;
  onMove: (index: number, by: number) => void;
  onAdd: () => void;
}) {
  const set = (index: number, row: Row) =>
    onChange(rows.map((each, at) => (at === index ? row : each)));

  return (
    <div className="flex flex-col gap-2">
      <Text variant="caption" tone="muted">
        Images, in the order the model is handed them
      </Text>

      {rows.length === 0 && (
        <Text variant="body" tone="muted">
          Nothing is sent. This run is text only.
        </Text>
      )}

      {rows.map((row, index) => (
        <div
          key={row.key}
          className="flex flex-wrap items-center gap-2 rounded-none border border-line p-2"
        >
          <span className="w-6 shrink-0 text-center font-body text-xs text-muted tabular-nums">
            {index + 1}
          </span>

          {row.url ? (
            <MediaThumb
              nodeId={row.node}
              url={row.url}
              name={row.name}
              isVideo={row.isVideo}
              aspect="portrait"
              className="w-14 shrink-0 rounded-none border border-line"
            />
          ) : (
            <span className="flex h-[4.7rem] w-14 shrink-0 items-center justify-center rounded-none border border-dashed border-line bg-surface-alt" />
          )}

          <div className="flex min-w-40 flex-1 flex-col gap-1">
            <Text variant="caption" className="truncate">
              {row.name}
            </Text>
            <div className="flex items-center gap-2">
              <Input
                aria-label={`Model input for image ${index + 1}`}
                value={row.field}
                onValueChange={(field: string) => set(index, { ...row, field })}
                list="run-send-fields"
                className="min-w-0 flex-1"
              />
              <Select
                aria-label={`What image ${index + 1} is for`}
                options={ROLES.map((role) => ({ value: role, label: role }))}
                value={row.role}
                onValueChange={(role: string) => set(index, { ...row, role })}
                className="shrink-0"
              />
            </div>
          </div>

          <div className="flex items-center gap-1">
            <Button
              intent="ghost"
              size="sm"
              aria-label={`Move image ${index + 1} earlier`}
              disabled={index === 0}
              onClick={() => onMove(index, -1)}
            >
              ↑
            </Button>
            <Button
              intent="ghost"
              size="sm"
              aria-label={`Move image ${index + 1} later`}
              disabled={index === rows.length - 1}
              onClick={() => onMove(index, 1)}
            >
              ↓
            </Button>
            <Button
              intent="ghost"
              size="sm"
              aria-label={`Remove image ${index + 1}`}
              onClick={() => onChange(rows.filter((_, at) => at !== index))}
            >
              <TrashIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
            </Button>
          </div>
        </div>
      ))}

      {/* The fields this run already binds, offered as completions rather than as
          the only choices — a datalist suggests, a select would decide, and this
          app has no registry to decide from. */}
      <datalist id="run-send-fields">
        {fields.map((field) => (
          <option key={field} value={field} />
        ))}
      </datalist>

      <div>
        <Button intent="ghost" size="sm" onClick={onAdd}>
          Add an image
        </Button>
      </div>
    </div>
  );
}

/** A stored send, as a row. */
function rowOf(send: RunSend, index: number): Row {
  return {
    key: `${send.node}:${index}`,
    field: send.field,
    role: send.role ?? "reference",
    node: send.node,
    name: send.name,
    url: send.url,
    isVideo: (send.content_type ?? "").startsWith("video/"),
  };
}

/**
 * A picked file, as a row — taking its field and role from the row before it.
 *
 * A new image is almost always another reference beside the ones already there,
 * and an empty field would be a payload that submits nowhere. Where there is no
 * row to copy, the fallback names the field every image model in the registry
 * happens to use; it is a starting point that the box next to it can be typed
 * over, not a claim about what the model accepts.
 */
function added(file: FileEntry, current: Row[]): Row {
  const last = current.at(-1);
  return {
    key: `${file.id}:new:${current.length}`,
    field: last?.field ?? "image_input",
    role: last?.role ?? "reference",
    node: file.id,
    name: file.name,
    url: file.url,
    isVideo: file.kind === "video",
  };
}

/** The stored sends in the shape the editor compares against — what is written. */
function sentOf(sends: RunSend[]) {
  return sends.map((send) => ({
    field: send.field,
    role: send.role,
    node: send.node,
  }));
}

function promptText(prompt: unknown): string {
  if (prompt == null) return "";
  return typeof prompt === "string" ? prompt : JSON.stringify(prompt, null, 2);
}

/** A parameter value as text: a string as itself, anything else as its JSON. */
function paramText(value: unknown): string {
  if (typeof value === "string") return value;
  // `undefined` has no JSON, and a row whose box held the literal text
  // "undefined" would write that string back on the next save.
  return value === undefined ? "" : JSON.stringify(value);
}

/**
 * The plan as it will be written — the version, origin and anything else the
 * record carries, with the four editable fields over the top.
 *
 * **`PATCH /plan` replaces the plan whole**, so what is not carried through here
 * is dropped. `origin` in particular has to survive: a reconstructed plan that
 * quietly became an authored one would be a record claiming somebody wrote words
 * that were read off a request document.
 */
function planOf(
  plan: RunPlan | null,
  prompt: string,
  structured: boolean,
  params: [string, string][],
  note: string,
): RunPlan {
  return {
    version: plan?.version ?? 1,
    origin: plan?.origin ?? "authored",
    ...plan,
    prompt: structured ? JSON.parse(prompt) : prompt,
    params: Object.fromEntries(
      params
        .filter(([key]) => key !== "")
        .map(([key, value]) => [key, paramValue(value)]),
    ),
    note: note === "" ? null : note,
  };
}

/** Text back to a value: JSON if it reads as JSON, the text itself otherwise. */
function paramValue(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
