import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  Alert,
  Button,
  Drawer,
  Field,
  IconButton,
  Input,
  Select,
  Text,
  Toggle,
  ToggleGroup,
} from "@ansavva/design-system";

import { createRun, getModels } from "../../apis/studio";
import { LoadError } from "../common/LoadError";
import { PlusIcon } from "../common/icons";
import { useResource } from "../../hooks/useResource";
import type { ModelEntry, RunKind, RunPlan, SnapshotProp } from "../../types";
import { runPath } from "../../utils/location";

/**
 * The output filename, as the API will store it.
 *
 * Mirrors `generate.slugify` — the same character class and the same trim — so
 * the field can show what the file will be called rather than what was typed.
 * A **courtesy**, not the check: the API slugifies again on the way out, and it
 * is the authority. (It also substitutes `output` for an empty stem, which this
 * deliberately does not: an empty box means "no name", not "call it output".)
 */
export function outputStem(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** A value a param can hold on its own. Anything else came from a list or a map. */
function isScalar(value: unknown): value is string | number | boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

/**
 * The plan a fresh draft starts with: the model's own defaults, and nothing else.
 *
 * **Three kinds of key are dropped, for three different reasons.** `refreshed`
 * is when the snapshot was taken — metadata sitting among the props, which is
 * why anything walking a snapshot has to skip it by name. `prompt` is carried
 * beside the params rather than inside them, and a copy in both would be two
 * answers to what the model is being asked. The entry's image fields are
 * **sends**, never params: an image reaches a provider as a presigned URL minted
 * from a node id (hard rule #3), so a params row naming one would be a second,
 * unchecked path to the same field.
 *
 * Non-scalar defaults go too. Every one of them in the registry today is `[]` —
 * an empty list standing in for "no images yet" — and seeding it would write an
 * empty array into a payload that the send rows are what fill.
 */
export function seedPlan(entry: ModelEntry): RunPlan {
  const images = entry.images ?? {};
  const skip = new Set(
    ["refreshed", "prompt", images.refs, images.start, images.end].filter(
      (key): key is string => typeof key === "string",
    ),
  );

  const params: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(entry.snapshot ?? {})) {
    if (skip.has(key)) continue;
    // `refreshed` is a bare string; every real prop is an object. Guarding on
    // the shape as well as the name keeps a future sibling key out too.
    if (!prop || typeof prop !== "object") continue;
    const value = (prop as SnapshotProp).default;
    if (isScalar(value)) params[key] = value;
  }

  return { version: 1, origin: "authored", prompt: "", params };
}

interface Props {
  projectId: string;
  /**
   * The project's cast, offered as this run's.
   *
   * **A run's characters are set HERE or never.** `POST /api/runs` takes them
   * and no route changes them afterwards, so a run created without any can
   * never cite one — and every template does, by position. The strip did not
   * offer them at all, which made every run the app created uncitable and the
   * template picker permanently disabled.
   */
  characters?: Array<{ id: string; slug: string; display_name?: string }>;
}

/**
 * Starting a run from the app: a strip above the runs, and a draft.
 *
 * **It creates the smallest legal run and leaves.** `POST /api/runs` needs only
 * a project, a kind and a model; the prompt, the params and the images are all a
 * `PATCH` away — so a composer that collected them here before the record
 * existed would be a second implementation of `RunPlanEditor`, which is already
 * correct against a real record and is where a re-run or a CLI-made draft is
 * edited too. This asks the three questions the API cannot proceed without, and
 * the editor asks the rest on the draft's own page.
 *
 * **No dialog, deliberately.** The house pattern for creating a record is
 * `CreateEntityDialog`, and this does not follow it: a modal that opens onto a
 * form and then navigates somewhere else is a step that exists only to be
 * dismissed. The strip is where the runs are, and pressing it lands in the
 * editor.
 *
 * Nothing here spends. A draft is hidden from listings until it is submitted and
 * is discardable from its own page, so an abandoned one costs a row.
 */
export function NewRunStrip({ projectId, characters = [] }: Props) {
  const navigate = useNavigate();
  const kindLabel = useId();

  // The registry is per-deploy rather than per-library, so the key carries no
  // id: two projects on the same page would share this answer.
  const load = useCallback(() => getModels(), []);
  const models = useResource(["models"], load);

  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<RunKind>("image");
  const [modelKey, setModelKey] = useState<string | null>(null);
  const [name, setName] = useState("");
  /**
   * Who this run is about, in the order a prompt counts them.
   *
   * `{character.1.…}` is the first of these, so the ORDER is the payload and
   * this is an array rather than a set — the same reason a run's sends are.
   */
  const [cast, setCast] = useState<string[]>([]);

  /**
   * **The project's cast is the run's, until somebody says otherwise.**
   *
   * A run in a project about one person is almost always about that person, and
   * making somebody re-state it every time is the kind of default that gets
   * skipped and then produces a run nothing can cite. Deselecting is one click;
   * remembering to select is not.
   *
   * Seeded when the strip opens rather than held: closing it and opening it
   * again is a fresh start, which is what Cancel means everywhere else here.
   */
  /**
   * **Keyed on the ids, not the array.** `characters` defaults to `[]`, which is
   * a NEW array on every render, so an effect depending on it re-ran forever —
   * set state, re-render, fresh default, set state. It did not fail the suite;
   * it exhausted memory and the runner was killed, which reads as a hang rather
   * than as a bug in this file.
   */
  const castKey = characters.map((each) => each.id).join(",");
  useEffect(() => {
    if (open) setCast(castKey ? castKey.split(",") : []);
  }, [open, castKey]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sorted by key: the map arrives in `models.json` order, which is the order
  // they were added rather than anything a reader would predict.
  const offered = useMemo(
    () =>
      Object.values(models.data ?? {})
        .filter((entry) => entry.kind === kind)
        .sort((a, b) => a.key.localeCompare(b.key)),
    [kind, models.data],
  );

  const entry = offered.find((each) => each.key === modelKey) ?? null;
  const stem = outputStem(name);

  async function create() {
    if (!entry) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createRun({
        project: projectId,
        kind: entry.kind,
        // The Replicate `owner/name`, not the registry key — `POST /api/runs`
        // records the model the provider is called by, and `engine` is the
        // skill that documents it.
        model: entry.model,
        engine: entry.skill,
        ...(stem ? { name: stem } : {}),
        ...(cast.length ? { characters: cast } : {}),
        plan: seedPlan(entry),
      });
      // `editing` rather than a query parameter: it is a one-shot instruction to
      // the page being opened, not a state its URL should carry into a share
      // link or a refresh.
      navigate(runPath(projectId, created.id), { state: { editing: true } });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /**
   * A plus above the list, and the form arrives in a drawer.
   *
   * Three shapes in three days, and each one answered the last: a form standing
   * permanently open across a tab that is mostly read; then a button that
   * swapped itself for the form in place, which pushed the run list down the
   * page every time it opened; now a plus where "make one of these" belongs —
   * top-right, above the thing it makes — and the form beside the list rather
   * than on top of it. The promote panel is the same drawer, so the two things
   * this page can create are asked for the same way.
   */
  const trigger = (
    // `label` IS the accessible name — IconButton takes the words out of the
    // box and puts them in the accessibility tree, so there is no `title` to
    // add and nothing here is unnamed.
    <IconButton label="New run" onClick={() => setOpen(true)}>
      <PlusIcon />
    </IconButton>
  );

  if (!open) return trigger;

  return (
    <>
      {trigger}
      <Drawer.Root
        open
        onOpenChange={(next: boolean) => {
          if (next) return;
          // Nothing here is typed prose — two choices and an optional name —
          // so a dismissal is taken at face value rather than guarded the way
          // the promote form's is.
          setOpen(false);
        }}
      >
        <Drawer.Backdrop />
        <Drawer.Panel className="w-full max-w-md overflow-y-auto">
          {models.error ? (
            <LoadError
              what="the model registry"
              message={models.error}
              onRetry={models.reload}
            />
          ) : (
            <NewRunForm />
          )}
        </Drawer.Panel>
      </Drawer.Root>
    </>
  );

  function NewRunForm() {
    return (
    <div className="flex flex-col gap-3 p-3">
      <Text variant="title">New run</Text>
      {/* `field-row`: this row carries a `Toggle`, which sets no height of its
          own, so it needs the row rule rather than the global one. See
          `app.css` — one control height, decided in one place. */}
      <div className="field-row flex flex-wrap items-end gap-2">
        {/* **Not a `Field`**, unlike its neighbours. `Field.Label` renders a
            `<label htmlFor>` pointing at the control that read the field's
            context, and `ToggleGroup` does not read it — so the label would
            address an id nothing carries. A caption the group names as its own
            label says the same thing and is true. */}
        <div className="flex flex-col gap-xs">
          {/* The same type as `Field.Label` next door, so the two labels sit on
              one line rather than a pixel apart. */}
          <Text id={kindLabel} as="span" className="font-body text-sm font-medium text-ink">
            Kind
          </Text>
          {/* Single-select, and the pressed one cannot be unpressed into
              nothing: a run is an image or a video, and there is no third
              state for the model list to be filtered by. */}
          <ToggleGroup.Root
            aria-labelledby={kindLabel}
            value={[kind]}
            onValueChange={(next: string[]) => {
              const chosen = (next[0] ?? kind) as RunKind;
              setKind(chosen);
              // The chosen model belongs to the old kind's list, and a stale
              // selection that no longer appears in the Select would leave the
              // button armed against a model nobody can see.
              if (chosen !== kind) setModelKey(null);
            }}
          >
            <Toggle value="image" className="rounded-none">
              Image
            </Toggle>
            <Toggle value="video" className="rounded-none">
              Video
            </Toggle>
          </ToggleGroup.Root>
        </div>

        <div className="min-w-56">
          <Field.Root name="model">
            <Field.Label>Model</Field.Label>
            {/* Labelled by the registry key, which is what the skills and the
                CLI call it. The Replicate id is what gets sent. */}
            <Select
              options={offered.map((each) => ({ value: each.key, label: each.key }))}
              value={modelKey}
              placeholder={models.loading ? "Loading models…" : "Choose a model"}
              disabled={models.loading || offered.length === 0}
              onValueChange={setModelKey}
            />
          </Field.Root>
        </div>

        {/* **Offered only when the project has a cast to offer.** A project
            with no characters is a real thing — a plate, a title card — and a
            control with nothing in it is worse than no control. */}
        {characters.length > 0 && (
          <div className="min-w-56">
            <Field.Root name="run-characters">
              <Field.Label>Characters</Field.Label>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {characters.map((each) => {
                  const at = cast.indexOf(each.id);
                  return (
                    <Button
                      key={each.id}
                      size="sm"
                      intent={at >= 0 ? "primary" : "secondary"}
                      onClick={() =>
                        setCast((current) =>
                          at >= 0
                            ? current.filter((id) => id !== each.id)
                            : [...current, each.id],
                        )
                      }
                    >
                      {/* The position, because it is what a prompt cites:
                          `{character.1.top}` is whichever of these is first. */}
                      {at >= 0 ? `${at + 1}. ` : ""}
                      {each.display_name || each.slug}
                    </Button>
                  );
                })}
              </div>
            </Field.Root>
          </div>
        )}

        <div className="min-w-48 flex-1">
          <Field.Root name="output-name">
            <Field.Label>Output name</Field.Label>
            <Input
              value={name}
              onValueChange={setName}
              placeholder="Optional"
            />
          </Field.Root>
        </div>

        {/* One flex item, so the pair wraps together rather than Cancel
            dropping to a line of its own under a row it belongs to.
            `md`, not `sm`: `sm` is 32 and is the package's deliberate opt-in to
            a smaller target, which is not what a row of 44s wants. */}
        <div className="flex items-center gap-2">
          <Button disabled={!entry || busy} onClick={() => void create()}>
            {busy ? "Creating…" : "Create draft"}
          </Button>
          <Button intent="secondary" disabled={busy} onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </div>

      {/* The one thing here a reader cannot see for themselves: the name they
          typed is not quite the name it will have. */}
      {stem && stem !== name.trim() && (
        <Text variant="caption" tone="muted">
          Saved as “{stem}”.
        </Text>
      )}

      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not create this draft</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}
      </div>
    );
  }
}
