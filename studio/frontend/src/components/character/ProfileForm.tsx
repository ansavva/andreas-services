import { useCallback, useMemo, useRef, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Collapsible,
  Field,
  Input,
  Separator,
  Switch,
  Text,
} from "@ansavva/design-system";

import type { CharacterIdentity, CharacterProfile, ProfileValue } from "../../types";
import { AutoTextarea } from "../common/AutoTextarea";
import { FormBar } from "../common/FormBar";
import { ChevronDownIcon } from "../common/icons";

interface Props {
  /** Slug and display name — saved by a different route from the bible. */
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

/**
 * The record fields' section id. Leading space so no bible key can collide with it.
 *
 * **Titled "Record", not "Identity".** The bible has its own `identity:` key, and
 * this card sat directly above the section rendered from it — two cards, same
 * heading, in the rail and in the page. The two are not the same thing: this one
 * is how the row is addressed and whether a likeness may be published, while
 * `identity:` is age, build, height read and signature features. So the card that
 * had no name of its own takes one.
 */
const RECORD = " record";

/**
 * The bible's one derived-looking section, and the reason it is not derived.
 *
 * `text_identity_block` restates `identity`, `face`, `body`, `wardrobe` and
 * `consistency` as ~50-70 words of prose, for an engine driven from a start
 * frame that carries no reference images. It reads redundant because it *is*
 * redundant — deliberately.
 *
 * **It is a summary, not a derived value, and the difference decides the UI.**
 * A derived value is recomputed and should not be hand-edited; this one is
 * written by Claude, is lossy on purpose (only what a text-only engine cannot
 * infer), and is the source of truth for what actually reaches a prompt. So it
 * stays fully editable and gets no regenerate button — there is nothing to
 * regenerate it with. `GET /api/characters/<id>/textblock` returns the stored
 * paragraph, or the five sections as raw material when none is written yet.
 */
const SUMMARY_KEY = "text_identity_block";

/** What the summary restates — the marker below watches these and nothing else. */
const SUMMARISED = ["identity", "face", "body", "wardrobe", "consistency"] as const;

/**
 * What each section is for, in one line — **and nothing below section level**.
 *
 * The form renders every field the same way, which made a nine-character
 * `rendering.default_style` that every turnaround depends on look exactly
 * as important as three thousand characters of `face` prose that no code reads
 * at all. Both are worth having; they are not the same kind of thing, and the
 * screen said nothing about which was which.
 *
 * **Section level is deliberate, and it is the compromise this file already
 * argues for elsewhere.** Naming individual fields here would make the frontend
 * a second copy of a schema the pipeline owns — a field somebody adds would need
 * a deploy to appear, and a list of "fields a shoot reads" would drift silently
 * the first time `engine/turnaround.py` changed. A sentence about what a section is
 * for changes about as often as the section does.
 *
 * A key that is not here still renders, in the order the record gave it, marked
 * off-schema. That is what `corpus` was for months: a legacy key from the
 * pre-catalog migration, sitting in the form as an equal, refused by the API on
 * every save, and looking like part of the product.
 */
const SECTIONS: ReadonlyArray<{ key: string; hint: string }> = [
  {
    key: "identity",
    hint: "The card: age, build, height read, signature features. A turnaround states apparent age and height read in the prompt, because a reference set spanning years will not agree on either.",
  },
  {
    key: "face",
    hint: "Structure, skin, eyes, hair, facial hair. No code reads this — it is what a prompt gets written from, and what a finished render is read back against.",
  },
  {
    key: "body",
    hint: "Proportions. A turnaround states them in the prompt so the angle image's own build does not decide the figure's — a face angle takes what shows above a mid-chest crop, a body angle takes all of it.",
  },
  {
    key: "wardrobe",
    hint: "What the character usually wears. A turnaround takes the first tops entry for its plain-top angle; the rest is prompt material.",
  },
  {
    key: "rendering",
    hint: "The medium the character exists in — a per-render choice rather than part of who they are, which is why it is not folded into the face and body prose. A shoot reads default_style; framing and backgrounds are prompt material, like face and voice.",
  },
  {
    key: "consistency",
    hint: "must / never / drift_modes — the checklist a render is verified against, each drift paired with the fix to write into the next prompt. A shoot puts must in the prompt itself.",
  },
  {
    key: "voice",
    hint: "Language, accent, manner, delivery. Read when a prompt carries a spoken line — Seedance generates the audio in character.",
  },
  {
    key: SUMMARY_KEY,
    hint: "A 50-70 word paragraph for engines that carry no reference images, where the character has to survive as prose. It restates the appearance sections; nothing here can write it, because studio's API calls no model.",
  },
];

const SECTION_HINTS = new Map(SECTIONS.map((section) => [section.key, section.hint]));

/**
 * The sections in groups, because eight peers is a list and not a shape.
 *
 * Every top-level key was drawn identically and in whatever order DynamoDB
 * serialised the map in, so reading the screen meant holding eight unrelated
 * headings in your head and working out which mattered. They are not eight
 * unrelated things: four say what the character IS, three say how to render one
 * and how to check the result, and the last is a restatement of the first four.
 *
 * The group is presentation and only presentation — nothing about the stored
 * shape changes, and a key the API adds tomorrow lands in `OTHER` rather than
 * disappearing.
 */
const GROUPS: ReadonlyArray<{ label: string; blurb: string; keys: readonly string[] }> = [
  {
    label: "Appearance",
    blurb: "Who the character is. Style-agnostic on purpose — how to render them is the next group.",
    keys: ["identity", "face", "body", "wardrobe"],
  },
  {
    label: "Direction",
    blurb: "How to render, and how to tell whether the render is right.",
    keys: ["rendering", "consistency", "voice"],
  },
  {
    label: "Summary",
    blurb: "The appearance sections compressed into one pasteable paragraph.",
    keys: [SUMMARY_KEY],
  },
];

/** The group a key nobody planned for falls into, so it is never silently dropped. */
const OTHER = {
  label: "Not in the schema",
  blurb:
    "Keys the API does not validate. A save carrying one is refused whole, so these are shown rather than hidden.",
};

/**
 * The record's keys in the manifest's order, grouped, with the unknown last.
 *
 * Ordered here rather than trusted from the record because a DynamoDB map has no
 * order worth relying on — the sections arrived in whatever order the item was
 * serialised in, which is why `voice` used to sit above `face`.
 *
 * A group with nothing in it is dropped rather than drawn empty: a character
 * written before a section existed should read as a shorter form, not a form
 * with a hole in it.
 */
function groupSections(keys: readonly string[]) {
  const groups = GROUPS.map((group) => ({
    ...group,
    keys: group.keys.filter((key) => keys.includes(key)),
  })).filter((group) => group.keys.length > 0);

  const stray = keys.filter((key) => !SECTION_HINTS.has(key));
  return stray.length > 0 ? [...groups, { ...OTHER, keys: stray }] : groups;
}

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

  const groups = useMemo(() => groupSections(Object.keys(profile)), [profile]);
  const keys = useMemo(() => groups.flatMap((group) => group.keys), [groups]);

  /**
   * Whether the sections the summary restates have moved in this session.
   *
   * **Only this session, and that is not a shortcut.** A stale marker that
   * survived a reload would need the record to remember when the paragraph was
   * last written against which sections — stored derived state, which is the
   * thing `docs/ENTITY_MODEL.md` argues out of this table on the grounds that it
   * goes stale and nobody notices. What is honest without it is the case that
   * actually bites: rewriting a face and forgetting the paragraph that describes
   * it, in the same sitting, with both on screen.
   */
  const summaryStale = useMemo(
    () =>
      SUMMARISED.some(
        (key) => JSON.stringify(profileDraft[key]) !== JSON.stringify(profile[key]),
      ),
    [profile, profileDraft],
  );

  const identityDirty = useMemo(
    () => JSON.stringify(identityDraft) !== JSON.stringify(identity),
    [identity, identityDraft],
  );

  /** Per section, so a trigger and its rail entry can each say which one moved. */
  const dirtySections = useMemo(() => {
    const moved = new Set<string>();
    if (identityDirty) moved.add(RECORD);
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
    () => new Set([RECORD, ...keys.slice(0, 1)]),
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
    () => setOpen(allOpen ? new Set() : new Set([RECORD, ...keys])),
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
      {conflict && (
        <Alert.Root intent="warning">
          <Alert.Title>Could not save over a newer version</Alert.Title>
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

      {/*
        The rail is additive and desktop-only.

        The sections are the same components either way and the open set is the
        same state — the rail only opens and scrolls. So a phone loses a jump list
        it has no room for and nothing else, and there is no second layout to keep
        in step with the first.
      */}
      <div className="grid gap-4 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-6">
        <nav aria-label="Profile sections" className="hidden lg:block">
          {/* `top-14` clears the app header. */}
          <div className="sticky top-14 flex flex-col gap-1">
            <Button intent="secondary" size="sm" className="justify-start" onClick={toggleAll}>
              {allOpen ? "Collapse all" : "Expand all"}
            </Button>
            <Separator className="my-1" />
            <RailLink
              title="Record"
              open={open.has(RECORD)}
              dirty={dirtySections.has(RECORD)}
              onClick={() => goToSection(RECORD)}
            />
            {groups.map((group) => (
              <div key={group.label} className="flex flex-col">
                {/* The group's name is a label, not a link: there is nothing to
                    scroll to that its first section does not already reach. */}
                <Text variant="caption" tone="muted" className="px-3 pb-1 pt-3">
                  {group.label}
                </Text>
                {group.keys.map((section) => (
                  <RailLink
                    key={section}
                    title={humanise(section)}
                    open={open.has(section)}
                    dirty={dirtySections.has(section)}
                    onClick={() => goToSection(section)}
                  />
                ))}
              </div>
            ))}
          </div>
        </nav>

        <div className="flex min-w-0 flex-col gap-3">
          {/* The rail's twin for narrow screens: one control rather than a column
              of them, because down there the sections themselves are the list. */}
          <div className="flex lg:hidden">
            {/* `-ms-3` cancels the button's own `px-3` so its text starts on the
                same line as the section titles below it. Left indented, it read
                as belonging to nothing. */}
            <Button intent="secondary" size="sm" className="-ms-3" onClick={toggleAll}>
              {allOpen ? "Collapse all" : "Expand all"}
            </Button>
          </div>

          <ProfileSection
            id={RECORD}
            title="Record"
            dirty={identityDirty}
            open={open.has(RECORD)}
            onOpenChange={(next) => setOpenAt(RECORD, next)}
            innerRef={(node) => sectionRefs.current.set(RECORD, node)}
          >
            <RecordFields value={identityDraft} onChange={setIdentityDraft} />
          </ProfileSection>

          {groups.map((group) => (
            <div key={group.label} className="flex flex-col gap-3">
              {/* A heading and a line, not a box. The sections are already cards
                  and a card holding cards is the nesting this form spent a
                  rework getting rid of — see the note above about four borders
                  drawn with one signal. */}
              <div className="flex flex-col gap-1 pt-2">
                <Text variant="title">{group.label}</Text>
                <Text variant="caption" tone="muted">
                  {group.blurb}
                </Text>
              </div>

              {group.keys.map((key) => (
                <ProfileSection
                  key={key}
                  id={key}
                  title={humanise(key)}
                  hint={SECTION_HINTS.get(key)}
                  // Only the summary carries one, and only while the sections it
                  // restates are dirty in this session.
                  stale={key === SUMMARY_KEY && summaryStale}
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
          ))}

          {/*
            One bar, one revision number.

            There used to be two of each: a Save on the identity card and a
            second on the bible below it, with a "revision N" beside both showing
            the same number. They are still two writes — the page chains them —
            and that is not something a person should have to hold.

            Sticky on a phone because a bible is longer than a screen, and a save
            you have to scroll to reach is one people stop making. It sat at the
            top of the form before this, where it slid under the app header.
          */}
          <FormBar
            dirty={dirty}
            saving={busy}
            onSave={save}
            onRevert={revert}
            meta={`revision ${rev}`}
            error={conflict ? null : error}
            errorTitle="Could not save the profile"
            sticky
          />
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
  hint,
  stale = false,
  dirty,
  open,
  onOpenChange,
  innerRef,
  children,
}: {
  id: string;
  title: string;
  /** One line on what the section is for. Absent means the schema does not name it. */
  hint?: string;
  /** The summary's own flag: what it restates has moved since it was written. */
  stale?: boolean;
  dirty: boolean;
  open: boolean;
  onOpenChange: (next: boolean) => void;
  innerRef: (node: HTMLDivElement | null) => void;
  children: React.ReactNode;
}) {
  // The `Record` card passes no hint and is not off-schema — it is not a bible
  // section at all. Only a key that came out of `profile` can be one, and those
  // are the only sections rendered from the manifest.
  const offSchema = hint === undefined && id !== RECORD;
  return (
    // `scroll-mt-16` keeps the heading clear of the sticky save bar when the rail
    // scrolls to it.
    //
    // **The padding reset is an inline style, and it has to be.** `Card.Root`
    // carries `p-lg`, and the package merges a caller's classes with
    // `tailwind-merge` — which does not recognise this design system's t-shirt
    // spacing keys as spacing at all. `twMerge('… p-lg …', 'p-0')` returns
    // *both*, so which one applies is decided by their order in the generated
    // stylesheet, and `.p-lg` is emitted after `.p-0`. The className reset
    // silently lost: the card kept its 24px and the panel below added 24px more,
    // for 48px a side on a 390px screen. Same trap for `gap-sm` vs `gap-0`.
    // An inline style is not a preference here, it is the only deterministic
    // answer — the same reasoning `ConfirmDeleteButton` records for its fill.
    <Card.Root
      ref={innerRef}
      data-section={id}
      style={{ padding: 0, gap: 0 }}
      className="scroll-mt-16"
    >
      <Collapsible.Root open={open} onOpenChange={onOpenChange}>
        {/* `py` inline for the same reason — the trigger's own `py-sm` beat the
            `py-md` written here, which quietly made the tap target shorter than
            intended on the control this page is used through most. `px` is safe
            as a class: the trigger sets none of its own. */}
        <Collapsible.Trigger
          style={{ paddingBlock: "0.75rem" }}
          className="w-full justify-between px-4 text-base sm:px-6"
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate">{title}</span>
            {/* Named on the trigger rather than only inside the panel: a section
                the API will refuse has to be visible while the card is shut, or
                it is only found by saving and reading the error. */}
            {offSchema && (
              <Badge intent="warning" size="sm">
                Not in the schema
              </Badge>
            )}
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
              one platform.

              This div is mine, so its padding is plain classes with nothing to
              conflict with — 16px on a phone, 24px from `sm` up. A phone is
              where the width is worth something. */}
          <div className="flex flex-col gap-4 px-4 pb-4 text-ink sm:px-6 sm:pb-6">
            {hint && (
              <Text variant="caption" tone="muted">
                {hint}
              </Text>
            )}
            {stale && (
              <Alert.Root intent="warning">
                <Alert.Title>The sections this summarises have changed</Alert.Title>
                <Alert.Description>
                  Reread it — this paragraph is what a start-frame engine is given,
                  and nothing updates it on its own. It is written by hand, so there
                  is no regenerate: edit it here, or run{" "}
                  <code>studio character textblock</code> for the raw material.
                </Alert.Description>
              </Alert.Root>
            )}
            {offSchema && (
              <Alert.Root intent="warning">
                <Alert.Title>The API does not know this section</Alert.Title>
                <Alert.Description>
                  The bible is validated by section, so a save carrying this one is
                  refused whole. It is shown rather than hidden on purpose: dropping
                  it here would delete it on the next save that did go through.
                </Alert.Description>
              </Alert.Root>
            )}
            {children}
          </div>
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
      className={`flex items-center gap-2 rounded-none px-2 py-1.5 text-left font-body text-sm transition-colors
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
    <ChevronDownIcon
      className={`size-4 shrink-0 fill-none stroke-current stroke-[1.5] transition-transform
                  motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
    />
  );
}

/**
 * Slug and display name.
 *
 * **Renaming here moves nothing.** No object is copied, no run document is
 * rewritten, and every reference, binding and default-set entry keeps pointing at
 * the same node ids: the slug is a label on one row, and the root folder's name
 * changes in the same transaction. It was a sweep over four pools plus a rewrite
 * pass over every run that cited the old path.
 */
function RecordFields({
  value,
  onChange,
}: {
  value: CharacterIdentity;
  onChange: (next: CharacterIdentity) => void;
}) {
  return (
    <>
      {/* **One field, where there were two.** A character carried a `slug` —
          library-unique, the address a person typed — beside a display name for
          prose, and keeping them in step was the reader's problem. Identity is a
          UUID and this is a label: not unique, not an address, and renaming it
          copies no objects and strands nothing. */}
      <Field.Root name="name">
        <Field.Label>Name</Field.Label>
        <Input value={value.name} onValueChange={(name) => onChange({ ...value, name })} />
        <Field.Description>What this character is called. Renaming copies no objects.</Field.Description>
      </Field.Root>
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
          <AutoTextarea value={text} onValueChange={(next: string) => onChange(path, next)} />
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
        <AutoTextarea
          value={value.map((item) => String(item ?? "")).join("\n")}
          minRows={2}
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
      intent="secondary"
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
              intent="secondary"
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

/**
 * Dotted paths whose string value wants a box rather than a line.
 *
 * **The threshold was 100 characters, which is a desktop answer.** A single-line
 * `Input` shows about 40 characters on a phone, so everything from 40 to 100 was
 * a value you had to scroll sideways through a one-line box to read. 48 is a
 * little over one phone line: past that, a box that grows is strictly better,
 * and `AutoTextarea` means a box is never taller than it needs to be on a wide
 * screen either.
 */
const WANTS_A_BOX = 48;

function collectLongPaths(value: ProfileValue, path: string[]): Set<string> {
  const found = new Set<string>();

  if (typeof value === "string") {
    if (value.includes("\n") || value.length > WANTS_A_BOX) found.add(path.join("."));
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
