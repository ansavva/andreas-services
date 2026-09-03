import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  Alert,
  Badge,
  Button,
  Field,
  Input,
  Select,
  Text,
} from "@ansavva/design-system";

import { EmptyState } from "../common/EmptyState";

import { ApiError } from "../../apis/client";
import {
  getCharacterSelection,
  getCharacters,
  getModel,
  getModelSchema,
  getProject,
  patchRunPlan,
  patchRunSends,
  previewPlanPrompt,
} from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type {
  FileEntry,
  ModelEntry,
  ModelSchema,
  RunPlan,
  RunRecord,
  RunSend,
  SelectionEntry,
} from "../../types";
import { AutoTextarea } from "../common/AutoTextarea";
import { RunCast } from "./RunCast";
import { TemplatePicker } from "./TemplatePicker";
import { TokenizedPromptEditor } from "../common/TokenizedPromptEditor";
import type { PromptToken } from "../common/TokenizedPromptEditor";
import { Filled, PreviewBox } from "../common/PromptPreview";
import {
  PROMPT_FIELDS,
  docWithFields,
  fieldsOf,
  parsePrompt,
} from "../scene/motionPrompt";
import { TrashIcon } from "../common/icons";
import { MediaPicker } from "../browse/MediaPicker";
import { MediaThumb } from "../media/MediaThumb";
import { SchemaParams, describedKeys } from "./SchemaParams";

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
/**
 * An expanded prompt, with each citation marked where it landed.
 *
 * The spans come from the API — `reference.expand_cast_parts` records them
 * while it fills, so they are the same walk that produced the text rather than
 * a search after the fact. Rendered with the same `Filled` the reference spec
 * preview uses, because it is the same question on both screens: which of these
 * words can I go and change.
 */
function Expanded({
  prompt,
  spans,
}: {
  prompt: string;
  spans: Array<{ name: string; start: number; end: number }>;
}) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const span of spans) {
    if (span.start > at) parts.push(<span key={`t${at}`}>{prompt.slice(at, span.start)}</span>);
    parts.push(
      <Filled key={span.start} label={`{${span.name}}`} name={span.name}>
        {prompt.slice(span.start, span.end)}
      </Filled>,
    );
    at = span.end;
  }
  if (at < prompt.length) parts.push(<span key="tail">{prompt.slice(at)}</span>);
  return <>{parts}</>;
}

//: What a run plan may cite off a character. The same six values a reference
//: angle fills from a bible — `reference.character_values` is the one thing
//: that produces them, on both surfaces.
/**
 * What `{character.N.…}` may cite.
 *
 * **`build` and `must` name a VARIANT and the bare form is refused**, because
 * the bible answers both differently for a face than for a body — a face crops
 * at mid-chest, so the proportions below it are noise, and the checklist gets a
 * different intro. That used to be decided by a `group` column on the template;
 * defaulting silently is how a face prompt ends up describing legs.
 */
const CHARACTER_FIELDS = [
  "top",
  "style",
  "age",
  "identity_block",
  "build.face",
  "build.body",
  "must.face",
  "must.body",
];

export function RunPlanEditor({
  run,
  onSaved,
  onChanged,
  onCancel,
}: {
  run: RunRecord;
  /** The updated run, straight off the response — the page swaps it in. */
  /** The plan was saved. The editor is done and the page closes it. */
  onSaved: (updated: RunRecord) => void;
  /**
   * The record changed under the editor, which stays open.
   *
   * **Separate from `onSaved`, and it has to be.** Editing the cast is a write
   * on the run, but it is not finishing the plan — routing it through `onSaved`
   * closed the editor mid-edit and threw away the prompt in the box, which is
   * the opposite of what pressing a character chip means.
   */
  onChanged: (updated: RunRecord) => void;
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
    // **Does it PARSE as a document — not: is it a JS object.** This read
    // `typeof run.plan.prompt !== "string"`, and `studio prompt` emits the
    // compiled document as a JSON *string*, which is what `--prompt-json`
    // stores. So every properly authored plan took the prose branch and was
    // edited as raw JSON in a textarea — the exact thing this form exists to
    // stop. Viewing was unaffected, because `parsePrompt` takes either.
    () => parsePrompt(promptText(run.plan?.prompt)) !== null,
    [run.plan],
  );

  /**
   * Whether the document was STORED as a string, so it is saved back as one.
   *
   * A plan authored by `studio prompt --emit prompt` holds a string; one built
   * by an older path holds an object. Both parse; writing the wrong one back
   * would silently change the shape of a record this form was only meant to
   * reword.
   */
  const storedAsString = useMemo(
    () => typeof run.plan?.prompt === "string",
    [run.plan],
  );

  /**
   * **The template when there is one, the prompt when there is not.**
   *
   * A plan that was written as a template keeps both — the expanded text
   * because `plan_digest` has to cover what reaches the model, and the template
   * because otherwise the next edit opens onto finished prose with no way back
   * to what was typed. This is the half a person edits.
   */
  const [prompt, setPrompt] = useState(
    () => run.plan?.template ?? promptText(run.plan?.prompt),
  );
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

  /**
   * What the model is — its registry entry, and its LIVE input schema.
   *
   * **Once per mount, by hand, rather than through `useResource`.** The schema
   * route proxies Replicate on every call, so it must not be a cached query that
   * a refocus or a remount refires; it is asked when somebody opens this editor
   * and not again. The entry is asked in the same breath because the two are
   * read together and neither blocks anything.
   *
   * **Either failure degrades to the freeform rows rather than to nothing.**
   * `Promise.allSettled`, so a provider that is down loses the typed form and
   * keeps the image fields — and `asked` is what lets the form say so out loud
   * instead of silently drawing the old key/value editor.
   */
  const [model, setModel] = useState<{
    entry: ModelEntry | null;
    schema: ModelSchema | null;
    asked: boolean;
  }>({ entry: null, schema: null, asked: false });

  useEffect(() => {
    if (!run.model) return undefined;
    let live = true;
    void (async () => {
      const [entry, schema] = await Promise.allSettled([
        getModel(run.model),
        getModelSchema(run.model),
      ]);
      if (!live) return;
      setModel({
        entry: entry.status === "fulfilled" ? entry.value : null,
        schema: schema.status === "fulfilled" ? schema.value : null,
        asked: true,
      });
    })();
    return () => {
      live = false;
    };
  }, [run.model]);

  /**
   * The inputs that carry images, by name — skipped by the params form and
   * offered to the send rows.
   *
   * Hard rule #3 in the one place a person could break it by typing: an image is
   * a node this library already holds, and it reaches the provider as a
   * presigned URL minted at submit. A parameter box for `image_input` would be a
   * place to paste a URL, which `runs.py` refuses after the fact.
   */
  const imageFields = useMemo(
    () =>
      [
        model.entry?.images?.refs,
        model.entry?.images?.start,
        model.entry?.images?.end,
      ].filter((field): field is string => Boolean(field)),
    [model.entry],
  );

  /**
   * The schema, or `null` when there is nothing usable in it.
   *
   * **An empty `props` map is a failure wearing a 200.** `services/schema.py`
   * answers `{}, {}` when the provider cannot be reached, deliberately, so that a
   * fetch that 500s never stops a payload a person already approved — which
   * means "this model takes no inputs" and "nobody could ask" arrive here as the
   * same body. No model takes no inputs, so this reads it as the second.
   */
  const schema = useMemo(() => {
    const props = model.schema?.props ?? {};
    return Object.keys(props).length > 0 ? model.schema : null;
  }, [model.schema]);

  const typedKeys = useMemo(
    () => describedKeys(schema, new Set(imageFields)),
    [schema, imageFields],
  );

  /**
   * The parameters the typed form does not describe, kept as rows.
   *
   * **Forward-compatible on purpose.** A plan written by the CLI against a newer
   * schema, or by a version of this app that had no form at all, still has to be
   * editable — so a key the schema does not mention is shown rather than hidden,
   * and nothing here drops one.
   */
  const freeform = useMemo(
    () => params.filter(([key]) => !typedKeys.has(key)),
    [params, typedKeys],
  );

  const typedValues = useMemo(
    () => Object.fromEntries(params.filter(([key]) => typedKeys.has(key))),
    [params, typedKeys],
  );

  const setParam = useCallback((key: string, text: string | null) => {
    setParams((current) => {
      const at = current.findIndex(([each]) => each === key);
      // Unset, which is not the same as empty: the key leaves the map entirely,
      // so the model chooses and the plan does not claim a person did.
      if (text === null)
        return at === -1 ? current : current.filter((_, index) => index !== at);
      if (at === -1) return [...current, [key, text]];
      return current.map((row, index) =>
        index === at ? ([key, text] as [string, string]) : row,
      );
    });
  }, []);

  /**
   * The freeform rows back into the one ordered list.
   *
   * Typed keys first, which is the order they are drawn in. It only matters at
   * all because `params` is a list until it is written; with no schema in hand
   * every key is freeform and the list comes back exactly as it went in.
   */
  const setFreeform = useCallback(
    (next: [string, string][]) =>
      setParams((current) => [
        ...current.filter(([key]) => typedKeys.has(key)),
        ...next,
      ]),
    [typedKeys],
  );

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

  /**
   * **Exactly what will be saved as the plan's prompt.**
   *
   * Lifted out of `save` so the preview beside the fields and the write itself
   * are one expression rather than two opinions about the same thing — the
   * disagreement a second implementation produces is invisible afterwards,
   * because the run records the outcome and not the reasoning.
   *
   * A structured prompt is six fields and a camera block that compile into one
   * document, so what you are editing and what gets sent look nothing alike;
   * that is the whole reason this is worth showing.
   */
  /**
   * The cast, numbered by the run's own binding.
   *
   * `{character.1.top}` is the FIRST character bound to this run — the same
   * one-based rule `[Image1]` already follows on these prompts. Numbered rather
   * than named because a slug is an attribute a rename swaps, and every record
   * here names entity ids for exactly that reason.
   */
  // `cast`, not `characters`: the record's field is written at creation and
  // nowhere else, so a run built by adding a character's references binds its
  // photographs and records nobody. The API derives it from the bindings.
  const cast = (run.cast ?? run.characters ?? []).length;
  const castTokens = useMemo<PromptToken[]>(
    () =>
      Array.from({ length: cast }).flatMap((_unused, i) =>
        CHARACTER_FIELDS.map((field) => ({
          name: `character.${i + 1}.${field}`,
          kind: "computed" as const,
          hint: `character ${i + 1}`,
        })),
      ),
    [cast],
  );

  const nextPrompt = useMemo(
    () =>
      structured
        ? JSON.stringify(
            docWithFields(
              parsePrompt(promptText(run.plan?.prompt)) ?? {},
              promptFields,
              camera,
            ),
            null,
            2,
          )
        : prompt,
    [camera, prompt, promptFields, run.plan?.prompt, structured],
  );

  /**
   * The expansion, from the API, debounced.
   *
   * **Not computed here.** `reference.character_values` is what fills a
   * character into a prompt and it is deliberately the only thing that does —
   * a second opinion about what somebody's usual garment is would disagree
   * invisibly, because a run records the outcome and not the reasoning.
   */
  const [expanded, setExpanded] = useState<{
    prompt: string;
    spans: Array<{ name: string; start: number; end: number }>;
  } | null>(null);
  /**
   * Why the preview did not expand, when it did not.
   *
   * **A refusal used to be swallowed** — caught, dropped, and the unexpanded
   * text shown in its place — so a prompt citing a character the run does not
   * bind looked like a prompt that simply had not expanded yet, and the only
   * account of it arrived on save. That is the one thing a person needs told
   * here: the API's message names the citation and the range, which is exactly
   * the fix.
   */
  const [unfilled, setUnfilled] = useState<string | null>(null);
  useEffect(() => {
    if (structured) return;
    const timer = setTimeout(() => {
      void previewPlanPrompt(run.id, prompt)
        .then((got) => {
          setExpanded({ prompt: got.prompt, spans: got.spans });
          setUnfilled(null);
        })
        .catch((problem: Error) => {
          setExpanded(null);
          setUnfilled(problem.message);
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [cast, prompt, run.id, structured]);

  const save = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      let latest = run;

      // `planOf` parses when the plan holds an object and passes the string
      // through when it holds a string — so the record keeps the shape it had.
      // Parsed before anything is written, so a malformed document cannot leave
      // the plan saved and the images not — or the other way round.
      const plan = planOf(
        run.plan,
        nextPrompt,
        structured && !storedAsString,
        params,
        note,
      );
      // **The template goes with it, and the API expands it into `prompt`.**
      // Both are kept: the digest has to cover what reaches the model, and the
      // template has to survive or the next edit opens onto finished prose with
      // no way back to what was written.
      //
      // **And it is REMOVED when this run has no cast to expand against.** A
      // run duplicated from a templated one carries the original's template,
      // `planOf` spreads it through untouched, and the API expands whatever
      // template it is handed — so a stale one silently overwrote the prompt
      // and every edit was discarded on save. The template has to track what is
      // in the box or not be sent at all.
      if (!structured) {
        if (cast > 0) plan.template = prompt;
        else delete plan.template;
      }
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
    // `camera`, `promptFields` and `prompt` are what `nextPrompt` is computed
    // from, so listing it is enough — and listing it is what keeps the saved
    // prompt and the previewed one the same string.
    cast,
    nextPrompt,
    note,
    onSaved,
    prompt,
    params,
    rows,
    run,
    storedAsString,
    structured,
  ]);

  /**
   * Which model inputs to offer for a new image — what this run already binds,
   * plus the image fields the registry names for this model.
   *
   * **This used to be read off the run alone, and said why: there was no
   * registry here and there must not become one, because `models.json` was the
   * pipeline's file and a copy in this app would be a second answer that went
   * stale silently.** That reasoning was right about a copy and is no longer
   * about one. The registry moved into the API — `backend/studio_core/models.json`,
   * served by `routes/models.py` — precisely so there is ONE copy at runtime;
   * the pipeline reads it over HTTP too. Asking `GET /api/models/<name>` here is
   * reading that same copy, not making a second.
   *
   * What has not changed is what enforces it: a wrong field is refused at submit
   * by the live schema check. These are completions, not a decision.
   */
  const fields = useMemo(
    () =>
      Array.from(
        new Set([...rows.map((row) => row.field), ...imageFields].filter(Boolean)),
      ),
    [rows, imageFields],
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

  /**
   * Who a reference set can be picked from — the project's own characters, and
   * the whole library only when the project names none.
   *
   * The project's list is the answer nearly every time and it is already in
   * hand; asking `/api/characters` as well would be a second request whose top
   * result is what the project already said. A project with no involvement rows
   * is the case that needs the fallback: a run authored before anyone was
   * attached to it.
   */
  const { data: library } = useResource(
    project && project.characters.length === 0 ? ["characters"] : null,
    useCallback(() => getCharacters(), []),
  );

  const characters = useMemo(
    () =>
      project?.characters.length
        ? project.characters
        : (library ?? []).map((each) => ({
            id: each.id,
            slug: each.name,
            name: each.name,
          })),
    [project, library],
  );

  /**
   * The room left under this model's reference cap, or `null` where it has none.
   *
   * **This is not the check.** `GET /selection` refuses over its own cap and the
   * submit refuses again; this is what stops asking for eleven when the model
   * takes seven, so the refusal is rarer rather than reinterpreted here.
   */
  const roomForRefs = useMemo(() => {
    const cap = model.entry?.images?.max_refs;
    if (typeof cap !== "number") return null;
    return cap - rows.filter((row) => row.role === "reference").length;
  }, [model.entry, rows]);

  /**
   * What the FIRST image added to an empty run binds to.
   *
   * **A video model's first image is its start frame**, near enough always: the
   * frame-first workflow renders a still and animates it, so an empty video run
   * gaining an image is that handoff. Guessing `image_input` there produced a
   * payload that submitted nowhere, and the box beside it can still be typed
   * over. Where the registry could not be read this is `null` and the old
   * fallback stands.
   */
  const firstField = useMemo(
    () =>
      run.kind === "video"
        ? (model.entry?.images?.start ?? null)
        : (model.entry?.images?.refs ?? null),
    [run.kind, model.entry],
  );

  /**
   * A resolved selection, appended as reference rows.
   *
   * The field is the registry's answer for this model where there is one, and
   * otherwise whatever the rows already there are using — a selection landing on
   * a different input from the images beside it would be a payload nobody meant.
   */
  const appendSelection = useCallback(
    (selection: SelectionEntry[]) => {
      setRows((current) => {
        // Never onto a scalar. Without the guard the last fallback was the row
        // above — the start frame — and five reference images went into a field
        // that holds one.
        const scalars = [model.entry?.images?.start, model.entry?.images?.end]
          .filter(Boolean);
        const notScalar = (f: string | undefined) =>
          f && !scalars.includes(f) ? f : undefined;
        const field =
          model.entry?.images?.refs ??
          notScalar([...current].reverse().find((row) => row.role === "reference")?.field) ??
          notScalar(current.at(-1)?.field) ??
          "image_input";
        return [
          ...current,
          ...selection.map((entry, index) => ({
            key: `${entry.node}:selected:${current.length + index}`,
            field,
            role: "reference",
            node: entry.node,
            name: entry.name ?? entry.node,
            url: entry.url ?? undefined,
            isVideo: false,
          })),
        ];
      });
    },
    [model.entry],
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
          <Alert.Title>Could not save the plan</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {/*
        **The prompt, and what it compiles to, side by side** — the treatment the
        reference spec cards have. A structured prompt is six fields plus a
        camera block that become one document, so the thing being edited and the
        thing being sent look nothing alike; a prose one wraps differently in a
        textarea than it reads as a payload. Below `xl` they stack.
      */}
      <div className="grid gap-3 xl:grid-cols-2">
      <div className="flex flex-col gap-3">
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
          {/* The description ABOVE the box, and the same type as the preview
              beside it. It sat underneath at `text-xs` while the preview was
              `text-sm` with its description on top, so two boxes showing the
              same sentence started at different heights and read at different
              sizes — which looks like a rendering fault rather than a pair. */}
          <Field.Description>
            {cast > 0
              ? `Type { to cite one of this run's ${cast} character(s). Expanded when you save.`
              : "Saved as the sentence it is. This run binds no character to cite."}
          </Field.Description>
          {/*
            **Picking a template fills the box and stops.**

            It is what the turnaround was, minus the fan-out: an angle was a
            prompt plus a description plus tags, and the only thing that could
            use one rendered all fourteen at once. Choosing here does not save
            and does not submit — the prompt lands as text a person reads,
            changes and approves, which is where hard rule #2 has always put
            the decision.

            Offered whatever this run binds. Whether a template needs a cast is
            a property of its prose — one built from blocks alone needs none —
            so the picker says it per template rather than hiding the list.
          */}
          <div className="pb-1">
            <TemplatePicker onPick={setPrompt} cast={cast} />
          </div>
          {/*
            **The tokenized editor only when there is a cast to cite.**

            It is the same editor the reference spec uses — a run's prompt was a
            plain textarea, so a `{` typed into it was a brace on its way to a
            model, which is what somebody trying to template one found. But a
            run that binds no character has nothing to offer: a menu with no
            options is worse than no menu, and a plain sentence needs no pills.
          */}
          {cast > 0 ? (
            <TokenizedPromptEditor
              value={prompt}
              onValueChange={setPrompt}
              tokens={castTokens}
              ariaLabel="Prompt"
            />
          ) : (
            <AutoTextarea
              value={prompt}
              onValueChange={setPrompt}
              minRows={4}
              className="font-mono text-sm leading-6"
            />
          )}
        </Field.Root>
      )}
      </div>

      <PreviewBox
        name="plan-prompt-preview"
        label="Preview"
        description={
          structured
            ? "The document these fields compile to. This is what the plan stores."
            : "Expanded against this run's cast. This is what the plan stores."
        }
        ariaLabel="Plan prompt preview"
      >
        {structured ? (
          nextPrompt
        ) : expanded ? (
          <Expanded prompt={expanded.prompt} spans={expanded.spans} />
        ) : (
          nextPrompt
        )}
      </PreviewBox>

      {/* **Named, and fixable in the same place.** A citation the run cannot
          fill is the commonest thing wrong with a prompt started from a
          template, and the commonest cause is a cast that has not been chosen
          — so the message and the control that answers it sit together. */}
      {!structured && unfilled && (
        <Alert.Root intent="warning">
          <Alert.Title>This will not expand yet</Alert.Title>
          <Alert.Description>{unfilled}</Alert.Description>
        </Alert.Root>
      )}

      {!structured && (
        <RunCast
          runId={run.id}
          projectId={run.project}
          value={run.characters ?? []}
          onSaved={onChanged}
        />
      )}
      </div>

      <div className="flex flex-col gap-3">
        <Text variant="caption" tone="muted">
          Parameters
        </Text>

        {schema && (
          <SchemaParams
            schema={schema}
            skip={new Set(imageFields)}
            values={typedValues}
            onSet={setParam}
          />
        )}

        {model.asked && !schema && (
          // Said out loud rather than degraded quietly: the boxes below look the
          // same either way, and "this model takes these inputs" and "nobody
          // could ask" are different claims to be making at somebody.
          <Text variant="caption" tone="muted">
            Could not read {run.model}&rsquo;s inputs, so parameters here are a
            name and a value. The payload is still checked against the live
            schema at submit.
          </Text>
        )}

        <Params
          rows={freeform}
          onChange={setFreeform}
          heading={schema ? "Anything else this model takes" : undefined}
        />
      </div>

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
        images={model.entry?.images ?? {}}
        onChange={setRows}
        onMove={move}
        onAdd={() => setPicking(true)}
        helper={
          <CharacterRefs
            choices={characters}
            room={roomForRefs}
            onAppend={appendSelection}
          />
        }
      />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button intent="secondary" size="sm" onClick={onCancel} disabled={busy}>
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
              ...files.map((file) => added(file, current, firstField, model.entry?.images ?? {})),
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
 * The parameters the schema does not describe, as rows.
 *
 * **A key-value editor rather than a JSON box**, because the values are a flat
 * map of knobs — aspect ratio, quality, duration — and typing braces around
 * three of them to change one is the kind of edit a text box makes and a form
 * does not.
 *
 * **It stays below the typed form rather than being replaced by it.** A schema
 * this app cannot draw, a key a newer model grew, and a plan the CLI wrote
 * against either are all still editable here; a form that showed only what it
 * understood would silently hide the rest of somebody's plan.
 */
function Params({
  rows,
  onChange,
  heading,
}: {
  rows: [string, string][];
  onChange: (next: [string, string][]) => void;
  /** Only when a typed form sits above and these rows need distinguishing. */
  heading?: string;
}) {
  const set = (index: number, pair: [string, string]) =>
    onChange(rows.map((row, at) => (at === index ? pair : row)));

  return (
    <div className="flex flex-col gap-2">
      {heading !== undefined && (
        <Text variant="caption" tone="muted">
          {heading}
        </Text>
      )}

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
            intent="secondary"
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
          intent="secondary"
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
  images,
  onChange,
  onMove,
  onAdd,
  helper,
}: {
  rows: Row[];
  fields: string[];
  /** What the registry says this model's image inputs are, and their arity. */
  images: NonNullable<ModelEntry["images"]>;
  onChange: (next: Row[]) => void;
  onMove: (index: number, by: number) => void;
  onAdd: () => void;
  /** The other way to add images — a character's references, in one gesture. */
  helper?: ReactNode;
}) {
  const set = (index: number, row: Row) =>
    onChange(rows.map((each, at) => (at === index ? row : each)));

  /**
   * Scalar image inputs that more than one row names.
   *
   * The registry says which fields hold ONE image (`images.start`,
   * `images.end`); anything past the first is discarded on the way to the
   * provider. Read off the rows being edited rather than the saved run, so it
   * appears and clears as the fields change.
   */
  const scalars = [images.start, images.end].filter(Boolean) as string[];
  const overloaded = scalars
    .map((field) => ({ field, count: rows.filter((r) => r.field === field).length }))
    .filter((f) => f.count > 1);

  /**
   * Move every row past the first off an overloaded field onto the reference
   * input.
   *
   * The FIRST keeps it: that is the one the provider would actually have
   * received, and the one a start frame is meant to be. Repointing all of them
   * would throw the start frame away instead of rescuing the references.
   */
  const repoint = () => {
    if (!images.refs) return;
    const kept = new Set<string>();
    onChange(
      rows.map((row) => {
        if (!overloaded.some((f) => f.field === row.field)) return row;
        if (!kept.has(row.field)) {
          kept.add(row.field);
          return row;
        }
        return { ...row, field: images.refs as string, role: "reference" as const };
      }),
    );
  };

  return (
    <div className="flex flex-col gap-2">
      <Text variant="caption" tone="muted">
        Images, in the order the model is handed them
      </Text>

      {/*
        **A scalar input named by more than one image is silently one image.**
        `bindings_of` keeps the first send for a start or end frame — that field
        is a string, and a list is a 422 from the provider — and drops the rest
        without a word. A run reached production with six images on `image` and
        went out with one, `reference_images` absent entirely.
        `_check_scalar_fields` refuses that at submit now, but the rows are
        already written that way on runs made before it, and a refusal at submit
        is later than a person can act on comfortably. So it is said here, with
        the correction one press away.
      */}
      {overloaded.length > 0 ? (
        <Alert.Root intent="warning">
          <Alert.Title>
            {overloaded[0]!.field} takes one image, and {overloaded[0]!.count} name it
          </Alert.Title>
          <Alert.Description>
            <div className="flex flex-col items-start gap-2">
              <span>
                {images.refs
                  ? `${overloaded[0]!.count - 1} of them would be dropped before the model saw them. References belong in ${images.refs}.`
                  : `${overloaded[0]!.count - 1} of them would be dropped before the model saw them, and this model takes no reference input.`}
              </span>
              {images.refs ? (
                <Button intent="secondary" onClick={repoint}>
                  Move the {overloaded[0]!.count - 1} reference(s) to {images.refs}
                </Button>
              ) : null}
            </div>
          </Alert.Description>
        </Alert.Root>
      ) : null}

      {rows.length === 0 && <EmptyState title="No images are sent." hint="This run is text only." />}

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
            {/* **Every control on this line, and every one of them 44px.**
                The three buttons used to be a sibling of this whole column, so
                they centred against the row — thumbnail and filename included —
                and sat fifteen pixels above the two controls they act on. The
                heights disagreed as well: an `Input` is 40 from the package's
                shared `controlBox`, a `Select` trigger is 44, and a `sm` Button
                is 32, so a row of them stepped down three times. */}
            <div className="field-row flex flex-wrap items-center gap-2">
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
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  intent="secondary"
                  size="sm"
                  aria-label={`Move image ${index + 1} earlier`}
                  disabled={index === 0}
                  onClick={() => onMove(index, -1)}
                >
                  ↑
                </Button>
                <Button
                  intent="secondary"
                  size="sm"
                  aria-label={`Move image ${index + 1} later`}
                  disabled={index === rows.length - 1}
                  onClick={() => onMove(index, 1)}
                >
                  ↓
                </Button>
                <Button
                  intent="secondary"
                  size="sm"
                  aria-label={`Remove image ${index + 1}`}
                  onClick={() => onChange(rows.filter((_, at) => at !== index))}
                >
                  <TrashIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      ))}

      {/* The fields this run binds and the ones the registry names for this
          model, offered as completions rather than as the only choices — a
          datalist suggests, a select would decide, and the entry lists the image
          inputs rather than every input a payload may carry. */}
      <datalist id="run-send-fields">
        {fields.map((field) => (
          <option key={field} value={field} />
        ))}
      </datalist>

      <div>
        <Button intent="secondary" size="sm" onClick={onAdd}>
          Add an image
        </Button>
      </div>

      {helper}
    </div>
  );
}

/**
 * A character's references, added as sends in one gesture.
 *
 * **What `--character` and `--pick` do on the command line**, which the app
 * could only do by finding each image in the picker and knowing which ones were
 * the identity. The selection is resolved by the API — default set, or a group,
 * or a tag — so which images a character means is answered in one place rather
 * than approximated here.
 *
 * **A refusal is shown and nothing is added.** `over_cap` is the whole point:
 * the route sends back the index it would have had to drop, and quietly keeping
 * the first seven of eleven would be a generation nobody could explain
 * afterwards — the same failure `characters.py` refuses a stale default set
 * over. Narrowing by group or tag is the way through, and it is a person's
 * choice to make.
 *
 * Inline, like every other control in this editor. No dialog.
 */
function CharacterRefs({
  choices,
  room,
  onAppend,
}: {
  choices: Array<{ id: string; name: string }>;
  /** Room left under the model's reference cap; `null` where it has none. */
  room: number | null;
  onAppend: (selection: SelectionEntry[]) => void;
}) {
  const [picked, setPicked] = useState("");
  const [group, setGroup] = useState("");
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dropped, setDropped] = useState<OverCapEntry[] | null>(null);

  // A sole character is the choice; anything else is asked. Derived rather than
  // seeded by an effect, so it holds the moment an async list lands.
  const who = picked || (choices.length === 1 ? (choices[0]?.id ?? "") : "");

  if (choices.length === 0) return null;

  const add = async () => {
    setBusy(true);
    setError(null);
    setDropped(null);
    try {
      if (room !== null && room <= 0) {
        setError(
          "This model's reference cap is already used up. Remove an image above first.",
        );
        return;
      }
      const { selection } = await getCharacterSelection(who, {
        group: group === "" ? undefined : group,
        tag: tag === "" ? undefined : tag,
        limit: room === null ? undefined : room,
      });
      onAppend(selection);
    } catch (err) {
      // The API's own sentence, not a rewrite of it: `support.structured` writes
      // one that names the counts, and a second wording here would be a second
      // claim about what happened.
      setError((err as Error).message);
      if (err instanceof ApiError && err.code === "over_cap") {
        const index = err.body?.index;
        setDropped(Array.isArray(index) ? (index as OverCapEntry[]) : null);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-none border border-dashed border-line p-2">
      <Text variant="caption" tone="muted">
        Or add a character&rsquo;s references
      </Text>

      <div className="field-row flex flex-wrap items-end gap-2">
        <Field.Root name="ref_character" className="min-w-40 flex-1">
          <Field.Label>Character</Field.Label>
          <Select
            options={choices.map((each) => ({
              value: each.id,
              label: each.name,
            }))}
            value={who}
            onValueChange={setPicked}
            placeholder="Pick one"
          />
        </Field.Root>
        <Field.Root name="ref_group" className="w-28">
          <Field.Label>Group</Field.Label>
          <Input value={group} onValueChange={setGroup} placeholder="any" />
        </Field.Root>
        <Field.Root name="ref_tag" className="w-28">
          <Field.Label>Tag</Field.Label>
          <Input value={tag} onValueChange={setTag} placeholder="any" />
        </Field.Root>
        <Button
          intent="secondary"
          size="sm"
          disabled={who === "" || busy}
          onClick={() => void add()}
        >
          {busy ? "Adding…" : "Add references"}
        </Button>
      </div>

      <Text variant="caption" tone="muted">
        {room === null
          ? "Whichever images the character's default set names, unless a group or tag narrows it."
          : `Room for ${room} more under this model's reference cap.`}
      </Text>

      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not add the references</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {dropped && (
        <Text variant="caption" tone="muted">
          The {dropped.length} that matched:{" "}
          {dropped.map((each) => each.name ?? each.node).join(", ")}
        </Text>
      )}
    </div>
  );
}

/** One row of an `over_cap` refusal's index — what it would have had to drop. */
interface OverCapEntry {
  node: string;
  name?: string | null;
  group?: string | null;
  description?: string | null;
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
 * A picked file, as a row.
 *
 * A new image is almost always another reference beside the ones already there,
 * and an empty field would be a payload that submits nowhere.
 *
 * ## It copied the row above, and that dropped five images
 *
 * Both field and role came off the previous row. A run whose first row is the
 * START FRAME therefore gave every image added after it `field: "image"` and
 * `role: "start"` — and `image` takes one value, so `bindings_of` kept the
 * first and discarded the rest. The page showed six images and the provider was
 * sent one, with `reference_images` absent entirely.
 *
 * So the role is decided first and the field follows FROM the role: a reference
 * goes to the model's reference input, a start frame to its start input. Only
 * when the registry says nothing does it fall back to copying, and never onto a
 * scalar field that is already taken.
 */
export function added(
  file: FileEntry,
  current: Row[],
  first: string | null,
  images: NonNullable<ModelEntry["images"]>,
): Row {
  const last = current.at(-1);
  // **The FIRST image is still whatever the registry says this model's images
  // bind to** — its start frame on a video run. That is the one case where
  // there is nothing to reason from, and it is the case `first` exists for.
  if (!last) {
    return {
      key: `${file.id}:new:${current.length}`,
      field: first ?? "image_input",
      role: "reference",
      node: file.id,
      name: file.name,
      url: file.url,
      isVideo: file.kind === "video",
    };
  }
  // A second START is a contradiction — that field holds one image — so an
  // image added after one is a reference, which is what it almost always is.
  const role = last.role === "start" || last.role === "end" ? "reference" : last.role;
  const scalars = [images.start, images.end].filter(Boolean);
  const copied = last.field && !scalars.includes(last.field) ? last.field : null;
  const field =
    role === "reference"
      ? (images.refs ?? copied ?? first ?? "image_input")
      : (copied ?? first ?? "image_input");
  return {
    key: `${file.id}:new:${current.length}`,
    field,
    role,
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
