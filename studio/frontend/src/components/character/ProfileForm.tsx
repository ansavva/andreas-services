import { useCallback, useMemo, useRef, useState } from "react";

import { Alert, Button, Field, Input, Switch, Text, Textarea } from "@ansavva/design-system";

import type { CharacterProfile, ProfileValue } from "../../types";

interface Props {
  profile: CharacterProfile;
  /** The revision the profile was read at — sent back with the save. */
  rev: number;
  /** Rejecting keeps the draft; a 409 is surfaced by the page above. */
  onSave: (profile: CharacterProfile, rev: number) => Promise<unknown>;
  /** Set when the last save lost a race. The draft is kept and the page offers a re-read. */
  staleRev?: boolean;
  onReload?: () => void;
}

/**
 * The bible, as fields.
 *
 * **Not a textarea over YAML, and that is the point of the whole rework.** The
 * profile used to be a document in a bucket whose shape studio was forbidden to
 * know, so the only honest editor was a text box. It is a validated map on a row
 * now, so it can be a form — and the difference is not cosmetic: a field cannot
 * be saved with a YAML syntax error in it, and two people describing two
 * different sections stop overwriting each other's document.
 *
 * **The form is still built from the value, not from a schema written out here.**
 * The sections the API validates are the pipeline's to change, and a frontend
 * that spelled every leaf out would need a deploy to show a field somebody added.
 * So this walks what it was given and picks a control per leaf:
 *
 * | Shape | Control |
 * |---|---|
 * | string | one line, or a box if the *saved* value was long — see `multiline` |
 * | boolean | a switch |
 * | number | a numeric line |
 * | list of strings | a box, one entry per line |
 * | list of maps | a repeated group, addable and removable |
 * | map | a section |
 *
 * Anything it cannot place is shown read-only rather than dropped, because
 * dropping it here would delete it on the next save.
 *
 * ## `rev`, and why the save is a compare-and-swap
 *
 * Every save sends the `rev` the profile was read at. A `rev` that has moved
 * comes back **409** and the write does not happen — where the old path re-read
 * the node's timestamp and refused if it had changed, which is a check followed
 * by a write with a window between them. The draft is kept on a 409 so the work
 * is not lost; what the page offers is a re-read, not a retry.
 */
export function ProfileForm({ profile, rev, onSave, staleRev = false, onReload }: Props) {
  const [draft, setDraft] = useState<CharacterProfile>(profile);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Which string leaves get a box instead of a line, decided **once** from the
   * profile as it arrived.
   *
   * Deciding it from the draft — "is this value long right now" — would swap the
   * element under the cursor the moment a line grew past the threshold, which
   * unmounts the input and takes focus with it. The saved value is a stable
   * answer to the same question.
   */
  const multiline = useRef<ReadonlySet<string>>(collectLongPaths(profile, []));

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(profile),
    [draft, profile],
  );

  const setAt = useCallback((path: string[], value: ProfileValue) => {
    setDraft((current) => setIn(current, path, value) as CharacterProfile);
  }, []);

  const save = useCallback(() => {
    setBusy(true);
    setError(null);
    onSave(draft, rev)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, [draft, onSave, rev]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Text variant="caption" tone="muted" className="tabular-nums">
          revision {rev}
        </Text>
        <div className="flex-1" />
        <Button
          intent="ghost"
          size="sm"
          disabled={!dirty || busy}
          onClick={() => setDraft(profile)}
        >
          Revert
        </Button>
        <Button size="sm" disabled={!dirty || busy} onClick={save}>
          {busy ? "Saving…" : dirty ? "Save profile" : "Saved"}
        </Button>
      </div>

      {staleRev && (
        <Alert.Root intent="warning">
          <Alert.Title>Somebody else changed this profile</Alert.Title>
          <Alert.Description>
            Your edits are still here and nothing was overwritten — the save was refused because
            the record moved on underneath it. Re-read it, then apply your changes again.
          </Alert.Description>
          {onReload && (
            <div className="pt-2">
              <Button size="sm" onClick={onReload}>
                Re-read the profile
              </Button>
            </div>
          )}
        </Alert.Root>
      )}

      {error && !staleRev && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not save the profile</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      <div className="flex flex-col gap-6">
        {Object.entries(draft).map(([key, value]) => (
          <ProfileNode
            key={key}
            label={key}
            path={[key]}
            value={value}
            multiline={multiline.current}
            onChange={setAt}
          />
        ))}
      </div>
    </div>
  );
}

interface NodeProps {
  label: string;
  path: string[];
  value: ProfileValue;
  multiline: ReadonlySet<string>;
  onChange: (path: string[], value: ProfileValue) => void;
}

/** One leaf, one list or one section — chosen by the shape of the value. */
function ProfileNode({ label, path, value, multiline, onChange }: NodeProps) {
  const name = path.join(".");
  const title = humanise(label);

  if (typeof value === "boolean") {
    return (
      // Not a `<label>`: `Switch.Root` renders a `<button>`, which is not a
      // labelable element, so the association would silently do nothing. The
      // name goes on the control itself.
      <div className="flex items-center gap-3">
        <Switch.Root
          checked={value}
          aria-label={title}
          onCheckedChange={(next) => onChange(path, next)}
        >
          <Switch.Thumb />
        </Switch.Root>
        <Text variant="body">{title}</Text>
      </div>
    );
  }

  if (typeof value === "number") {
    return (
      <Field.Root name={name}>
        <Field.Label>{title}</Field.Label>
        <Input
          type="number"
          value={String(value)}
          onValueChange={(next: string) => onChange(path, next === "" ? null : Number(next))}
        />
      </Field.Root>
    );
  }

  if (value === null || typeof value === "string") {
    const text = value ?? "";
    return (
      <Field.Root name={name}>
        <Field.Label>{title}</Field.Label>
        {multiline.has(name) ? (
          <Textarea
            value={text}
            rows={4}
            onValueChange={(next: string) => onChange(path, next)}
          />
        ) : (
          <Input value={text} onValueChange={(next: string) => onChange(path, next)} />
        )}
      </Field.Root>
    );
  }

  if (Array.isArray(value)) {
    // A list of maps is a repeated group; anything else is treated as a list of
    // scalars, one per line. A mixed list is neither, and falls to the scalar
    // form — which round-trips it as text rather than silently reshaping it.
    const shaped = value.filter((item) => isMap(item)) as Array<Record<string, ProfileValue>>;
    if (shaped.length > 0 && shaped.length === value.length) {
      return (
        <GroupList
          title={title}
          path={path}
          items={shaped}
          multiline={multiline}
          onChange={onChange}
        />
      );
    }

    return (
      <Field.Root name={name}>
        <Field.Label>{title}</Field.Label>
        {/* One entry per line. A list of short cues is what this shape always
            holds — signature features, accent cues, the never/must lists — and a
            row of inputs with add and remove buttons is more chrome than the
            content it wraps. */}
        <Textarea
          value={value.map((item) => String(item ?? "")).join("\n")}
          rows={Math.min(8, Math.max(2, value.length + 1))}
          onValueChange={(next: string) =>
            onChange(
              path,
              next
                .split("\n")
                .map((line) => line.trim())
                .filter((line) => line !== ""),
            )
          }
        />
        <Field.Description>One per line.</Field.Description>
      </Field.Root>
    );
  }

  if (isMap(value)) {
    return (
      <section className="flex flex-col gap-3 rounded-md border border-line bg-card p-3">
        <Text variant="title">{title}</Text>
        <div className="flex flex-col gap-3">
          {Object.entries(value).map(([childKey, childValue]) => (
            <ProfileNode
              key={childKey}
              label={childKey}
              path={[...path, childKey]}
              value={childValue}
              multiline={multiline}
              onChange={onChange}
            />
          ))}
        </div>
      </section>
    );
  }

  // Unreachable for anything JSON can carry, and kept anyway: a value this walker
  // cannot place must still be *shown*, because the save writes the whole draft
  // back and a leaf that was never rendered would be a leaf that was deleted.
  return (
    <Field.Root name={name}>
      <Field.Label>{title}</Field.Label>
      <Text variant="caption" tone="muted">
        {JSON.stringify(value)}
      </Text>
    </Field.Root>
  );
}

/**
 * A list of maps — `wardrobe.tops`, `consistency.drift_modes`.
 *
 * Addable and removable, because these are the two sections where the *number*
 * of entries is the edit: adding a garment or a drift mode is the ordinary thing
 * to want, and a list you can only retype is one people stop maintaining. A new
 * entry copies the keys of the first, with empty values, so the shape the API
 * validates against is preserved without this file knowing what it is.
 */
function GroupList({
  title,
  path,
  items,
  multiline,
  onChange,
}: {
  title: string;
  path: string[];
  items: Array<Record<string, ProfileValue>>;
  multiline: ReadonlySet<string>;
  onChange: (path: string[], value: ProfileValue) => void;
}) {
  const template = items[0] ?? {};

  return (
    <section className="flex flex-col gap-3 rounded-md border border-line bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <Text variant="title">{title}</Text>
        <Button
          intent="ghost"
          size="sm"
          onClick={() =>
            onChange(path, [
              ...items,
              Object.fromEntries(Object.keys(template).map((key) => [key, ""])),
            ])
          }
        >
          Add
        </Button>
      </div>

      {items.map((item, index) => (
        <div
          // Index-keyed on purpose: these entries have no id, and re-keying on
          // their contents would remount the field under the cursor on every
          // keystroke.
          key={index}
          className="flex flex-col gap-3 rounded-md border border-line p-3"
        >
          <div className="flex items-center justify-between gap-2">
            <Text variant="caption" tone="muted" className="tabular-nums">
              {index + 1}
            </Text>
            <Button
              intent="ghost"
              size="sm"
              onClick={() => onChange(path, items.filter((_, at) => at !== index))}
            >
              Remove
            </Button>
          </div>

          {Object.entries(item).map(([key, value]) => (
            <ProfileNode
              key={key}
              label={key}
              path={[...path, String(index), key]}
              value={value}
              multiline={multiline}
              onChange={onChange}
            />
          ))}
        </div>
      ))}
    </section>
  );
}

function isMap(value: ProfileValue): value is Record<string, ProfileValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `apparent_age` → `Apparent age`. The keys are the bible's own wording. */
function humanise(key: string): string {
  const spaced = key.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Dotted paths whose string value wants a box rather than a line. */
function collectLongPaths(value: ProfileValue, path: string[]): Set<string> {
  const found = new Set<string>();

  if (typeof value === "string") {
    if (value.includes("\n") || value.length > 100) found.add(path.join("."));
    return found;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      for (const each of collectLongPaths(item, [...path, String(index)])) found.add(each);
    });
    return found;
  }
  if (isMap(value)) {
    for (const [key, child] of Object.entries(value)) {
      for (const each of collectLongPaths(child, [...path, key])) found.add(each);
    }
  }
  return found;
}

/**
 * A copy of `source` with one leaf replaced — arrays stay arrays, maps stay maps.
 *
 * Immutable because the draft is React state and a mutation in place would not
 * re-render, and because `dirty` is a structural comparison against the profile
 * as it was read.
 */
function setIn(source: ProfileValue, path: string[], value: ProfileValue): ProfileValue {
  const [head, ...rest] = path;
  if (head === undefined) return value;

  if (Array.isArray(source)) {
    const index = Number(head);
    return source.map((item, at) => (at === index ? setIn(item, rest, value) : item));
  }

  const base = isMap(source) ? source : {};
  return { ...base, [head]: setIn(base[head] ?? null, rest, value) };
}
