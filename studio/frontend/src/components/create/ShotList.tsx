import { useRef, type ReactNode } from "react";

import { Button, Input, Switch, Text } from "@ansavva/design-system";

import type { ModelEntry, ModelSchema } from "../../types";
import { AutoTextarea } from "../common/AutoTextarea";
import { ArrowDownIcon, ArrowUpIcon, CloseIcon, PlusIcon } from "../common/icons";
import { useLiveSchema } from "./CreateChips";

/**
 * Multi-shot: the cuts inside one generation, as boxes under the prompt.
 *
 * **Kling's `multi_prompt` is a JSON array in a string field**, and a string
 * field is what the settings sheet drew — 1,500 characters of escaped JSON in
 * a growing textarea, with the one rule that refuses a submit (the beats'
 * seconds must add up to `duration`) invisible until the API said no.
 *
 * **It does not belong in the settings sheet at all.** These are prompts. They
 * run long, they are read and re-read and rewritten, and the sheet is a column
 * of one-line values behind a gear — the wrong shape and the wrong place for
 * the text that decides what the clip does. So the boxes sit under the prompt
 * box, in the create panel, where prose is written; the switch says whether
 * the clip is cut at all, and the plus adds the next cut.
 *
 * **The prompt above does not become redundant — it changes job.** It carries
 * what is true of every cut (the setting, the cast, the grade, the sound) and
 * the beats carry what happens. `services/prompt.py` compiles to exactly that
 * split, and stopped writing `Shot N (Ns): …` lines into the prompt when this
 * field carries them.
 *
 * The value written back is the same JSON string the model takes — these are a
 * view of that one field, not a new record shape, so a draft authored by the
 * CLI or by an agent opens here unchanged.
 */

/** One beat, as the model's own array holds it. */
export interface Shot {
  prompt: string;
  duration: number;
}

/**
 * The field's value as beats, or `null` when it is not a shot list at all.
 *
 * `null` is a real answer and not a failure: the field is a free string, so
 * something hand-written and half-finished can be in it, and the editor hands
 * those back to a plain textarea rather than replacing them with an empty
 * list. **Nothing parses its way to data loss here.**
 */
export function parseShots(value: unknown): Shot[] | null {
  if (value === undefined || value === null || value === "") return [];
  if (typeof value !== "string") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed)) return null;
  const out: Shot[] = [];
  for (const each of parsed) {
    if (!each || typeof each !== "object" || Array.isArray(each)) return null;
    const { prompt, duration } = each as Record<string, unknown>;
    if (typeof prompt !== "string") return null;
    if (duration !== undefined && typeof duration !== "number") return null;
    out.push({ prompt, duration: typeof duration === "number" ? duration : 0 });
  }
  return out;
}

/**
 * The beats in a value that IS one, and `null` for anything else.
 *
 * **Shaped, not named.** A run's record carries the plan's params and not the
 * registry entry that says which of them holds the cuts, so the read side
 * recognises a shot list by what it is — a list of `{prompt, duration}` —
 * rather than fetching an entry per run to be told its field is called
 * `multi_prompt`. Anything that is not one falls through to the pill or the
 * mono line it already had.
 *
 * **Two spellings of the same list, because two providers spell it
 * differently.** Replicate's proxy takes `multi_prompt` as a JSON string;
 * fal takes a real array, and a shot's seconds as a string. Both are the
 * timeline somebody wrote, so both read back as beats — the read side is
 * the one place that has to know about both, since the payload is whatever
 * its own provider took.
 */
export function shotListOf(value: unknown): Shot[] | null {
  const shots = Array.isArray(value)
    ? beatsOf(value)
    : typeof value === "string" && value.trim() !== ""
      ? parseShots(value)
      : null;
  return shots !== null && shots.length > 0 ? shots : null;
}

/**
 * A list of `{prompt, duration}` as beats, or `null` when it is not one.
 *
 * Read-only, and looser than `parseShots` about the seconds: fal spells a
 * shot's duration `"3"` where Replicate spells it `3`. Reading is where that
 * difference is absorbed. `parseShots` stays strict because it is the
 * editor's, and what the editor writes back goes on the wire.
 */
function beatsOf(parsed: unknown[]): Shot[] | null {
  const out: Shot[] = [];
  for (const each of parsed) {
    if (!each || typeof each !== "object" || Array.isArray(each)) return null;
    const { prompt, duration } = each as Record<string, unknown>;
    if (typeof prompt !== "string") return null;
    const seconds = secondsOf(duration);
    if (seconds === null) return null;
    out.push({ prompt, duration: seconds });
  }
  return out;
}

/** A shot's seconds however its provider wrote them; `null` for anything else. */
function secondsOf(duration: unknown): number | null {
  if (duration === undefined || duration === null) return 0;
  if (typeof duration === "number") return Number.isFinite(duration) ? duration : null;
  if (typeof duration === "string" && duration.trim() !== "") {
    const value = Number(duration);
    return Number.isFinite(value) ? value : null;
  }
  return null;
}

/**
 * The cuts a plan carries, whichever param holds them.
 *
 * Recognised by SHAPE — a run's record has the params and not the registry
 * entry that would name the field. See `shotListOf`.
 */
export function shotsOf(params: Record<string, unknown> | undefined): Shot[] | null {
  for (const value of Object.values(params ?? {})) {
    const shots = shotListOf(value);
    if (shots) return shots;
  }
  return null;
}

/**
 * The beats as plain text — what Copy prompt hands over.
 *
 * Where a timeline replaced the prompt there is no `plan.prompt` to copy, and
 * Copy prompt put an empty clipboard on the one kind of run whose whole text
 * is the beats. The seconds come with them: they are half of what a beat says.
 */
export function shotsAsText(shots: Shot[]): string {
  return shots
    .map((shot, at) => `Shot ${at + 1} (${shot.duration}s)\n${shot.prompt}`)
    .join("\n\n");
}

/** Beats back to the wire: the JSON string the model's field takes. */
export function serializeShots(shots: Shot[]): string | undefined {
  return shots.length === 0 ? undefined : JSON.stringify(shots);
}

/** Which input holds the cuts on this model, per the registry. */
export function shotsField(entry: ModelEntry | null): string | null {
  const video = (entry?.video ?? {}) as { shots?: unknown };
  return typeof video.shots === "string" ? video.shots : null;
}

/** How many cuts this model allows — `video.max_cuts`, or no ceiling. */
function maxCuts(entry: ModelEntry): number | null {
  const video = (entry.video ?? {}) as { max_cuts?: unknown };
  return typeof video.max_cuts === "number" ? video.max_cuts : null;
}

/**
 * The clip's length, which the beats have to add up to.
 *
 * What is SET if anything is, and the model's own default otherwise — because
 * an untouched duration chip writes nothing and the run still goes out at the
 * default the chip is showing. Reading only `params` would call a correct
 * five-second timeline short of nothing. The live schema first and the
 * registry snapshot behind it, the same order `resolveChips` reads them in.
 */
export function durationOf(
  entry: ModelEntry,
  schema: ModelSchema | null,
  params: Record<string, unknown>,
): number | null {
  for (const name of ["duration", "duration_seconds"]) {
    const set = params[name];
    if (typeof set === "number") return set;
    if (typeof set === "string" && set.trim() !== "" && !Number.isNaN(Number(set))) {
      return Number(set);
    }
    const live = schema?.props?.[name]?.default;
    if (typeof live === "number") return live;
    // `refreshed` is a string on the same map, so a snapshot entry is only a
    // prop when it is an object.
    const snap = entry.snapshot?.[name];
    if (snap && typeof snap === "object" && typeof snap.default === "number") {
      return snap.default;
    }
  }
  return null;
}

/** The seconds a new beat opens with: what is left over, or one. */
function nextSeconds(shots: Shot[], duration: number | null): number {
  if (duration === null) return 1;
  const spare = duration - shots.reduce((sum, shot) => sum + shot.duration, 0);
  return spare >= 1 ? spare : 1;
}

/**
 * The two beats the switch opens with, splitting the clip between them.
 *
 * Two rather than one, because one cut is not a multi-shot — and because the
 * seconds are then already right, which is the rule that is easiest to break
 * and most expensive to find out about.
 */
function openingShots(duration: number | null): Shot[] {
  const half = duration === null ? 1 : Math.max(1, Math.floor(duration / 2));
  const rest = duration === null ? 1 : Math.max(1, duration - half);
  return [
    { prompt: "", duration: half },
    { prompt: "", duration: rest },
  ];
}

/**
 * The switch, and the boxes under it.
 *
 * Drawn only for a model whose registry entry names a shots field, so there
 * is no switch on a model that cannot be cut.
 */
export function ShotsPanel({
  entry,
  params,
  onParams,
}: {
  entry: ModelEntry;
  params: Record<string, unknown>;
  onParams: (next: Record<string, unknown>) => void;
}) {
  const field = shotsField(entry);
  const schema = useLiveSchema(entry.model);
  /**
   * What was typed before the switch was turned off.
   *
   * A switch that throws prose away is a switch nobody dares press. Off
   * unsets the field — the model must not receive an empty array — and the
   * beats wait here for the way back. Not state: nothing renders from it.
   */
  const remembered = useRef<Shot[] | null>(null);
  const value = field === null ? undefined : params[field];
  const parsed = parseShots(value);
  /**
   * **Derived from the value, never held in state.** Held, it went stale the
   * first time it mattered: this panel mounts with the create bar, and
   * pressing Edit on a draft seeds the params into it afterwards — so a draft
   * with four beats opened with the switch off and its beats invisible but
   * still on the wire. There is no third state to remember anyway; beats in
   * the field IS multi-shot, and the last `×` turns the switch off with it.
   */
  const on = parsed === null || parsed.length > 0;

  if (field === null) return null;

  const duration = durationOf(entry, schema, params);
  const set = (next: string | undefined) => {
    const out = { ...params };
    if (next === undefined) delete out[field];
    else out[field] = next;
    onParams(out);
  };

  const flip = (next: boolean) => {
    if (next) {
      set(serializeShots(remembered.current ?? openingShots(duration)));
      remembered.current = null;
      return;
    }
    remembered.current = parsed !== null && parsed.length > 0 ? parsed : null;
    set(undefined);
  };

  return (
    <div className="flex flex-col gap-2 px-1" data-shots="">
      {/* Wrapping, and the tally unbreakable: at 390px the caption takes two
          lines and `8s of 8s` was stacking one word per line beside it. */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Switch.Root aria-label="Multi-shot" checked={on} onCheckedChange={flip}>
          <Switch.Thumb />
        </Switch.Root>
        <Text as="span" variant="caption" tone="muted" className="min-w-0 flex-1">
          {on
            ? // The answer to "why am I writing two prompts", where the
              // question gets asked. The compiler keeps the same split.
              "Multi-shot — the prompt above is the setting; each shot is a cut inside it"
            : "Multi-shot — cut between shots inside one clip"}
        </Text>
        {on && (
          <Text
            as="span"
            variant="caption"
            className={`ml-auto shrink-0 whitespace-nowrap ${tallyOf(parsed, duration).tone}`}
          >
            {tallyOf(parsed, duration).text}
          </Text>
        )}
      </div>
      {on && (
        <ShotList value={value} duration={duration} max={maxCuts(entry)} onChange={set} />
      )}
    </div>
  );
}

/**
 * One beat's box: the label, whatever the surface puts on its right, and the
 * beat's text under both.
 *
 * **The same box wherever a shot is drawn** — the create panel's editor, the
 * opened run's rail, a feed row. A shot read back should look like the shot
 * that was written, and three near-identical layouts drifting apart is how
 * that stops being true.
 */
export function ShotCard({
  label,
  right,
  children,
}: {
  label: string;
  right: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-line p-2" data-shot-card="">
      <div className="flex items-center justify-between gap-2">
        <Text as="span" variant="caption" tone="muted">
          {label}
        </Text>
        <span className="flex shrink-0 items-center gap-1">{right}</span>
      </div>
      {children}
    </div>
  );
}

/**
 * The beats, read-only — the run page and the feed row.
 *
 * `text` is how the surface draws a beat's prose: the feed clamps it the way
 * it clamps the prompt, and anywhere with room passes it through.
 */
export function ShotsRead({
  shots,
  text,
}: {
  shots: Shot[];
  text?: (value: string) => ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2" data-shots-read="">
      {shots.map((shot, at) => (
        <ShotCard
          key={at}
          label={`Shot ${at + 1}`}
          right={
            <Text as="span" variant="caption" family="mono" tone="muted">
              {shot.duration}s
            </Text>
          }
        >
          {text ? (
            text(shot.prompt)
          ) : (
            <Text variant="body" className="whitespace-pre-wrap">
              {shot.prompt}
            </Text>
          )}
        </ShotCard>
      ))}
    </div>
  );
}

/** The beats themselves: a box each, in order. */
export function ShotList({
  value,
  duration,
  max,
  onChange,
}: {
  /** The field's current value — the JSON string, or nothing. */
  value: unknown;
  /** The clip's length, which the beats must add up to. `null` when unset. */
  duration: number | null;
  /** The model's cut ceiling, from the registry. `null` where it has none. */
  max: number | null;
  onChange: (next: string | undefined) => void;
}) {
  const shots = parseShots(value);

  // Not a shot list: a textarea over exactly what is there, and no attempt to
  // interpret it. See `parseShots`.
  if (shots === null) {
    return (
      <div className="flex flex-col gap-1.5">
        <AutoTextarea
          aria-label="Shots"
          minRows={3}
          maxRows={12}
          value={String(value)}
          onValueChange={(text: string) => onChange(text === "" ? undefined : text)}
        />
        <Text variant="caption" className="text-danger">
          This is not a list of shots studio can read, so it is shown as text.
          The model takes a JSON array of {`{"prompt", "duration"}`}.
        </Text>
      </div>
    );
  }

  const full = max !== null && shots.length >= max;
  const set = (next: Shot[]) => onChange(serializeShots(next));

  return (
    <div className="flex flex-col gap-2" data-shot-list="">
      {shots.map((shot, at) => (
        <ShotCard
          key={at}
          label={`Shot ${at + 1}`}
          right={
            <>
              <Input
                aria-label={`Shot ${at + 1} seconds`}
                type="number"
                min={1}
                max={duration ?? undefined}
                value={shot.duration === 0 ? "" : String(shot.duration)}
                className="h-8 w-16 px-2 text-right text-sm"
                onValueChange={(text: string) =>
                  set(
                    shots.map((each, i) =>
                      i === at
                        ? { ...each, duration: text.trim() === "" ? 0 : Number(text) }
                        : each,
                    ),
                  )
                }
              />
              <Text as="span" variant="caption" tone="muted">
                s
              </Text>
              <Button
                intent="ghost"
                size="sm"
                aria-label={`Move shot ${at + 1} earlier`}
                disabled={at === 0}
                onClick={() => set(swap(shots, at, at - 1))}
              >
                <ArrowUpIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
              </Button>
              <Button
                intent="ghost"
                size="sm"
                aria-label={`Move shot ${at + 1} later`}
                disabled={at === shots.length - 1}
                onClick={() => set(swap(shots, at, at + 1))}
              >
                <ArrowDownIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
              </Button>
              <Button
                intent="ghost"
                size="sm"
                aria-label={`Remove shot ${at + 1}`}
                onClick={() => set(shots.filter((_, i) => i !== at))}
              >
                <CloseIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
              </Button>
            </>
          }
        >
          {/* The same growing box the prompt has, because it holds the same
              kind of writing: what happens, in prose, at whatever length it
              takes. */}
          <AutoTextarea
            aria-label={`Shot ${at + 1}`}
            minRows={2}
            maxRows={12}
            value={shot.prompt}
            placeholder="What happens in this cut"
            onValueChange={(text: string) =>
              set(shots.map((each, i) => (i === at ? { ...each, prompt: text } : each)))
            }
          />
        </ShotCard>
      ))}

      <div>
        <Button
          intent="secondary"
          size="sm"
          disabled={full}
          title={full && max !== null ? `${max} shots is this model's most` : undefined}
          onClick={() =>
            set([...shots, { prompt: "", duration: nextSeconds(shots, duration) }])
          }
        >
          <PlusIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          Add a shot
        </Button>
      </div>
    </div>
  );
}

function swap(shots: Shot[], from: number, to: number): Shot[] {
  const out = [...shots];
  const [moved] = out.splice(from, 1);
  if (moved) out.splice(to, 0, moved);
  return out;
}

/**
 * The running total, and whether it will be refused.
 *
 * **Kling rejects a timeline whose beats do not sum to `duration` (E006)** and
 * studio refuses it before that, at submit. Either way the person finds out
 * after the draft is written; the arithmetic is two numbers and belongs beside
 * the boxes that produce it.
 */
export function tallyOf(
  shots: Shot[] | null,
  duration: number | null,
): { text: string; tone: string } {
  if (shots === null) return { text: "", tone: "text-muted" };
  const total = shots.reduce((sum, shot) => sum + shot.duration, 0);
  if (shots.length === 0) return { text: "", tone: "text-muted" };
  if (duration === null) {
    return { text: `${total}s across ${shots.length} shots`, tone: "text-muted" };
  }
  if (total === duration) return { text: `${total}s of ${duration}s`, tone: "text-muted" };
  const off = total - duration;
  return {
    text: `${total}s of ${duration}s — ${off > 0 ? `${off}s over` : `${-off}s short`}`,
    tone: "text-danger",
  };
}
