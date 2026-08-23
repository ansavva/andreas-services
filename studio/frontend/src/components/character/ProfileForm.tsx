import { useCallback, useMemo, useRef, useState } from "react";

import {
  Alert,
  Button,
  Card,
  Collapsible,
  Field,
  Input,
  Separator,
  Switch,
  Text,
  Textarea,
} from "@ansavva/design-system";

import type { CharacterIdentity, CharacterProfile, ProfileValue } from "../../types";

interface Props {
  /** Slug, display name and the consent flag — saved by a different route from the bible. */
  identity: CharacterIdentity;
  profile: CharacterProfile;
  /** The revision both were read at — sent back with the save. */
  rev: number;
  /** Rejecting keeps the draft. The page decides which routes to call, and in what order. */
  onSave: (
    changes: { identity?: CharacterIdentity; profile?: CharacterProfile },
    rev: number,
  ) => Promise<unknown>;
  /** The API's own 409 wording when the last save was refused, or null. */
  conflict?: string | null;
  onReload?: () => void;
}

/** The identity fields' section id. Leading space so no bible key can collide with it. */
const IDENTITY = " identity";

/**
 * The character record, as one form: who they are on top, then the bible.
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
 * | map | a titled group under a rule |
 *
 * Anything it cannot place is shown read-only rather than dropped, because
 * dropping it here would delete it on the next save.
 *
 * ## Sections collapse, and every section is one box deep
 *
 * A bible is long. Every top-level key used to be an open bordered card, any map
 * inside it another, and any list of maps a third with a fourth around each
 * entry — four nested boxes drawn with the same border on the same background,
 * which is depth signalled by repeating one signal. On a 390px screen it also
 * spent 72px of the width on padding.
 *
 * So: **one `Card.Root` per top-level section, and nothing nested inside it.**
 * Depth below that is a title over a `Separator`, and repeated entries are
 * separated rather than boxed. The sections themselves collapse, which is what
 * makes a whole bible legible on a phone instead of a scroll through all of it.
 *
 * `Collapsible` rather than `Accordion` because the open set has to be
 * *controlled* — the rail opens sections, "Expand all" opens every one, and
 * `Accordion.Root` is uncontrolled (`defaultValue` and nothing else). Its panel
 * keeps children mounted and marks them `inert` while closed, so collapsing a
 * section with edits in it never discards them.
 *
 * Two sections start open: identity, and the first of the bible. Opening all of
 * them is the old behaviour and its problem; opening none wastes a wide screen.
 *
 * ## `rev`, and why the save is a compare-and-swap
 *
 * Every save sends the `rev` the record was read at. A `rev` that has moved comes
 * back **409** and the write does not happen — where the old path re-read the
 * node's timestamp and refused if it had changed, which is a check followed by a
 * write with a window between them. The draft is kept on a 409 so the work is not
 * lost; what the form offers is a re-read, not a retry.
 */
export function ProfileForm({ identity, profile, rev, onSave, conflict = null, onReload }: Props) {
  const [identityDraft, setIdentityDraft] = useState<CharacterIdentity>(identity);
  const [profileDraft, setProfileDraft] = useState<CharacterProfile>(profile);
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

  const keys = useMemo(() => Object.keys(profile), [profile]);

  const identityDirty = useMemo(
    () => JSON.stringify(identityDraft) !== JSON.stringify(identity),
    [identity, identityDraft],
  );

  /** Per section, so a trigger and its rail entry can each say which one moved. */
  const dirtySections = useMemo(() => {
    const moved = new Set<string>();
    if (identityDirty) moved.add(IDENTITY);
    for (const key of keys) {
      if (JSON.stringify(profileDraft[key]) !== JSON.stringify(profile[key])) moved.add(key);
    }
    return moved;
  }, [identityDirty, keys, profile, profileDraft]);

  const profileDirty = useMemo(
    () => keys.some((key) => dirtySections.has(key)),
    [dirtySections, keys],
  );
  const dirty = identityDirty || profileDirty;

  const [open, setOpen] = useState<ReadonlySet<string>>(
    () => new Set([IDENTITY, ...keys.slice(0, 1)]),
  );

  const setOpenAt = useCallback((section: string, next: boolean) => {
    setOpen((current) => {
      const updated = new Set(current);
      if (next) updated.add(section);
      else updated.delete(section);
      return updated;
    });
  }, []);

  const allOpen = open.size === keys.length + 1;
  const toggleAll = useCallback(
    () => setOpen(allOpen ? new Set() : new Set([IDENTITY, ...keys])),
    [allOpen, keys],
  );

  const sectionRefs = useRef(new Map<string, HTMLDivElement | null>());

  /**
   * The rail's click: open the section, then bring it to the top.
   *
   * Scrolling to a *closed* section is the failure this avoids — it lands on a
   * heading with nothing under it. Only the target opens, and it opens downward,
   * so nothing above it moves and the scroll needs no second frame to settle.
   */
  const goToSection = useCallback(
    (section: string) => {
      setOpenAt(section, true);
      sectionRefs.current.get(section)?.scrollIntoView({ block: "start", behavior: "smooth" });
    },
    [setOpenAt],
  );

  const revert = useCallback(() => {
    setIdentityDraft(identity);
    setProfileDraft(profile);
    setError(null);
  }, [identity, profile]);

  const setAt = useCallback((path: string[], value: ProfileValue) => {
    setProfileDraft((current) => setIn(current, path, value) as CharacterProfile);
  }, []);

  const save = useCallback(() => {
    setBusy(true);
    setError(null);
    onSave(
      {
        ...(identityDirty ? { identity: identityDraft } : {}),
        ...(profileDirty ? { profile: profileDraft } : {}),
      },
      rev,
    )
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, [identityDirty, identityDraft, onSave, profileDirty, profileDraft, rev]);

  return (
    <div className="flex flex-col gap-4">
      {/*
        One bar, one revision number, and it follows the page down.

        There used to be two of each: a Save on the identity card and a second on
        the bible below it, with a "revision N" beside both showing the same
        number. They are still two writes — the page chains them — and that is not
        something a person should have to hold.

        Sticky because a bible is longer than a screen, and a save you have to
        scroll back up to reach is one people stop making. Three items, so it
        stays one row at 390px.
      */}
      <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-line bg-bg py-2">
        <Text variant="caption" tone="muted" className="tabular-nums">
          revision {rev}
        </Text>
        <div className="flex-1" />
        <Button intent="ghost" size="sm" disabled={!dirty || busy} onClick={revert}>
          Revert
        </Button>
        <Button size="sm" disabled={!dirty || busy} onClick={save}>
          {busy ? "Saving…" : dirty ? "Save" : "Saved"}
        </Button>
      </div>

      {conflict && (
        <Alert.Root intent="warning">
          <Alert.Title>That did not go through</Alert.Title>
          <Alert.Description>
            {conflict} Your edits are still here and nothing was overwritten. Re-read the record,
            then apply them again.
          </Alert.Description>
          {onReload && (
            <div className="pt-2">
              <Button size="sm" onClick={onReload}>
                Re-read the character
              </Button>
            </div>
          )}
        </Alert.Root>
      )}

      {error && !conflict && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not save</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      {/*
        The rail is additive and desktop-only.

        The sections are the same components either way and the open set is the
        same state — the rail only opens and scrolls. So a phone loses a jump list
        it has no room for and nothing else, and there is no second layout to keep
        in step with the first.
      */}
      <div className="grid gap-4 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-6">
        <nav aria-label="Profile sections" className="hidden lg:block">
          {/* `top-14` clears the sticky save bar above it. */}
          <div className="sticky top-14 flex flex-col gap-1">
            <Button intent="ghost" size="sm" className="justify-start" onClick={toggleAll}>
              {allOpen ? "Collapse all" : "Expand all"}
            </Button>
            <Separator className="my-1" />
            {[IDENTITY, ...keys].map((section) => (
              <RailLink
                key={section}
                title={section === IDENTITY ? "Identity" : humanise(section)}
                open={open.has(section)}
                dirty={dirtySections.has(section)}
                onClick={() => goToSection(section)}
              />
            ))}
          </div>
        </nav>

        <div className="flex min-w-0 flex-col gap-3">
          {/* The rail's twin for narrow screens: one control rather than a column
              of them, because down there the sections themselves are the list. */}
          <div className="flex lg:hidden">
            <Button intent="ghost" size="sm" onClick={toggleAll}>
              {allOpen ? "Collapse all" : "Expand all"}
            </Button>
          </div>

          <ProfileSection
            id={IDENTITY}
            title="Identity"
            dirty={identityDirty}
            open={open.has(IDENTITY)}
            onOpenChange={(next) => setOpenAt(IDENTITY, next)}
            innerRef={(node) => sectionRefs.current.set(IDENTITY, node)}
          >
            <IdentityFields value={identityDraft} onChange={setIdentityDraft} />
          </ProfileSection>

          {keys.map((key) => (
            <ProfileSection
              key={key}
              id={key}
              title={humanise(key)}
              dirty={dirtySections.has(key)}
              open={open.has(key)}
              onOpenChange={(next) => setOpenAt(key, next)}
              innerRef={(node) => sectionRefs.current.set(key, node)}
            >
              <ProfileNode
                label={key}
                path={[key]}
                value={profileDraft[key] ?? null}
                multiline={multiline.current}
                onChange={setAt}
                headless
              />
            </ProfileSection>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * One top-level section: a card, a trigger spanning its whole width, and a panel
 * that keeps its children mounted while closed.
 *
 * `Card.Root` is stripped of its own padding and gap so the trigger can fill the
 * card. A header you can only hit on the text is a small target on a phone, and
 * this is the control a person uses most on this page.
 */
function ProfileSection({
  id,
  title,
  dirty,
  open,
  onOpenChange,
  innerRef,
  children,
}: {
  id: string;
  title: string;
  dirty: boolean;
  open: boolean;
  onOpenChange: (next: boolean) => void;
  innerRef: (node: HTMLDivElement | null) => void;
  children: React.ReactNode;
}) {
  return (
    // `scroll-mt-16` keeps the heading clear of the sticky save bar when the rail
    // scrolls to it.
    <Card.Root ref={innerRef} data-section={id} className="scroll-mt-16 gap-0 p-0">
      <Collapsible.Root open={open} onOpenChange={onOpenChange}>
        <Collapsible.Trigger className="w-full justify-between px-lg py-md text-base">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate">{title}</span>
            {/* A dot, not a word: it sits beside a heading that can already be
                long, and "unsaved" beside six of them is noise. The label is on
                the element for anyone not reading colour. */}
            {dirty && (
              <span
                role="img"
                aria-label="unsaved changes"
                className="size-1.5 shrink-0 rounded-full bg-accent"
              />
            )}
          </span>
          <Chevron open={open} />
        </Collapsible.Trigger>

        <Collapsible.Panel>
          {/* The panel's leaf paints its content `text-muted` — these are form
              fields, not prose about them. Set on this element rather than
              passed to `Collapsible.Panel` as a class for it to merge: the
              cascade settles it from a child no matter what the panel's own
              wrapper is, and 0.15.0 is a release that changed that wrapper on
              one platform. */}
          <div className="flex flex-col gap-4 px-lg pb-lg text-ink">{children}</div>
        </Collapsible.Panel>
      </Collapsible.Root>
    </Card.Root>
  );
}

function RailLink({
  title,
  open,
  dirty,
  onClick,
}: {
  title: string;
  open: boolean;
  dirty: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={open ? "true" : undefined}
      className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-left font-body text-sm transition-colors
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                    open
                      ? "bg-surface-alt text-ink"
                      : "text-muted hover:bg-surface-alt hover:text-ink"
                  }`}
    >
      <span className="min-w-0 flex-1 truncate">{title}</span>
      {dirty && (
        <span
          role="img"
          aria-label="unsaved changes"
          className="size-1.5 shrink-0 rounded-full bg-accent"
        />
      )}
    </button>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`size-4 shrink-0 fill-none stroke-current stroke-[1.5] transition-transform
                  motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

/**
 * Slug, display name and the consent flag.
 *
 * **Renaming here moves nothing.** No object is copied, no run document is
 * rewritten, and every reference, binding and default-set entry keeps pointing at
 * the same node ids: the slug is a label on one row, and the root folder's name
 * changes in the same transaction. It was a sweep over four pools plus a rewrite
 * pass over every run that cited the old path.
 */
function IdentityFields({
  value,
  onChange,
}: {
  value: CharacterIdentity;
  onChange: (next: CharacterIdentity) => void;
}) {
  return (
    <>
      <Field.Root name="slug">
        <Field.Label>Slug</Field.Label>
        <Input value={value.slug} onValueChange={(slug) => onChange({ ...value, slug })} />
        <Field.Description>
          Library-unique, and the address a person types. Changing it copies no objects.
        </Field.Description>
      </Field.Root>

      <Field.Root name="display_name">
        <Field.Label>Display name</Field.Label>
        <Input
          value={value.display_name}
          onValueChange={(displayName) => onChange({ ...value, display_name: displayName })}
        />
      </Field.Root>

      {/* Not a `<label>` — `Switch.Root` is a `<button>`, which is not labelable. */}
      <div className="flex items-center gap-3">
        <Switch.Root
          checked={value.fictional}
          aria-label="Fictional"
          onCheckedChange={(fictional) => onChange({ ...value, fictional })}
        >
          <Switch.Thumb />
        </Switch.Root>
        <Text variant="body">Fictional</Text>
      </div>
    </>
  );
}

interface NodeProps {
  label: string;
  path: string[];
  value: ProfileValue;
  multiline: ReadonlySet<string>;
  onChange: (path: string[], value: ProfileValue) => void;
  /**
   * Drop this node's own title.
   *
   * Set for a top-level section, whose title is already the card's trigger. A
   * heading repeated an inch below the one you just clicked is the duplication
   * this pass exists to remove.
   */
  headless?: boolean;
}

/** One leaf, one list or one group — chosen by the shape of the value. */
function ProfileNode({ label, path, value, multiline, onChange, headless = false }: NodeProps) {
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
          <Textarea value={text} rows={4} onValueChange={(next: string) => onChange(path, next)} />
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
          headless={headless}
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
      <div className="flex flex-col gap-3">
        {!headless && <GroupHeading title={title} />}
        {/* Indented on a wide screen and flush on a narrow one: the indent is
            what carries the nesting now that the border is gone, and 12px of it
            is 3% of a phone's width spent saying what the heading already says. */}
        <div className="flex flex-col gap-4 sm:ps-3">
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
      </div>
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

/** A title over a rule — the whole of what used to be a nested bordered card. */
function GroupHeading({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <Text variant="title">{title}</Text>
        {action}
      </div>
      <Separator />
    </div>
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
 *
 * Entries are separated rather than boxed. A border around each one, inside a
 * border around the list, inside a border around the section, is three rules
 * saying the same thing.
 */
function GroupList({
  title,
  path,
  items,
  multiline,
  onChange,
  headless = false,
}: {
  title: string;
  path: string[];
  items: Array<Record<string, ProfileValue>>;
  multiline: ReadonlySet<string>;
  onChange: (path: string[], value: ProfileValue) => void;
  headless?: boolean;
}) {
  const template = items[0] ?? {};

  const add = (
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
  );

  return (
    <div className="flex flex-col gap-3">
      {headless ? <div className="flex justify-end">{add}</div> : <GroupHeading title={title} action={add} />}

      {items.map((item, index) => (
        <div
          // Index-keyed on purpose: these entries have no id, and re-keying on
          // their contents would remount the field under the cursor on every
          // keystroke.
          key={index}
          className="flex flex-col gap-3"
        >
          {index > 0 && <Separator className="mt-1" />}
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
    </div>
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
 * re-render, and because the dirty check is a structural comparison against the
 * profile as it was read.
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
