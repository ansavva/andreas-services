import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Badge, Button, Select, Spinner, Text, Toggle, ToggleGroup } from "@ansavva/design-system";

import {
  addReference,
  getReferences,
  getTree,
  patchReference,
  setDefaultSet,
  type DefaultSetAck,
} from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { ENGINE_CAPS, type FileEntry, type ReferenceEntry } from "../../types";
import { ChipRow } from "../common/ChipRow";
import { CheckIcon } from "../common/icons";
import { objectPath } from "../../utils/location";
import { MediaThumb } from "../media/MediaThumb";
import { LoadError } from "../common/LoadError";

interface Props {
  characterId: string;
  /** The character's root node — where the `reference/` folder is looked for. */
  rootId: string;
  /** Marked on the grid. Held on the record because it is small, ordered and read on every shoot. */
  defaultSet: string[];
  /**
   * The character's revision, which `PATCH /default-set` compares and refuses on.
   *
   * Passed in rather than re-read here: the page already holds the record, and a
   * second copy fetched by this component would be the stale one exactly when it
   * matters. Writing without it is what #485 was.
   */
  rev: number;
  /**
   * The set and the revision the write answered with.
   *
   * A patch to merge, never a record to swap in — the route answers with three
   * fields, so replacing the page's record with it drops everything else the
   * character is.
   */
  onSaved: (ack: DefaultSetAck) => void;
}

/** The folder the starting layout puts reference images in. A convention, and checked as one. */
const REFERENCE_FOLDER = "reference";

/**
 * The reference pool: grouped, ordered, described, and rearrangeable.
 *
 * **Every one of those was a filename before.** `<slug>_<group>_<n>.png` carried
 * the group and the position, the bible's `references:` map carried the
 * description keyed on that same basename, and the two went out of step every
 * time either was renumbered. Group and order are attributes on a row now, so
 * regrouping copies no bytes, reordering is one write that touches neither
 * neighbour, and a description is a row's own field rather than a rewrite of the
 * whole bible.
 *
 * ## The grid is thumbnails; everything else is in the sheet
 *
 * Each entry used to be a card holding a bordered thumbnail, a name, badges and
 * an open textarea — three borders deep, and at `grid-cols-1` on a phone it made
 * one very wide, very short form per reference. A reference pool is something you
 * *look* at, so the grid is now the images at the same density as every other
 * media grid in this app, and the fields moved into a sheet that opens on tap.
 *
 * ## Reordering had to stop being drag-only
 *
 * Dragging wrote `{after: <node>}` and still does — `order` is gapped by 1000 and
 * the API takes the midpoint of that entry's order and the next one's, so a move
 * is one conditional write that rewrites no neighbours. What was wrong is that
 * dragging was the **only** way: `draggable` and `onDrop` are HTML5 drag events,
 * which no touch browser fires, so regrouping and reordering — the whole point of
 * this screen — silently did nothing on a phone.
 *
 * The sheet carries a group picker and move up/down, which send exactly the same
 * `{group, after}` the drag does. Drag stays as the accelerator it always was,
 * on the pointers that have it.
 *
 * ## The caps are a warning, not the check
 *
 * `GET /api/characters/<id>/selection` is what actually refuses an over-cap set,
 * with the index in the body, and it does so before any money is spent. What is
 * drawn here is the same arithmetic done early, so the refusal is visible while
 * the set is being built rather than at the point of a shoot. If an engine's cap
 * moves this warns slightly early or slightly late; it can never let one through.
 *
 * **It used to say so three times.** One badge per engine — `Kling 5/7`,
 * `Seedance 5/9`, `Nano Banana 5/14` — is one number and three comparisons, and
 * on a 390px screen the four of them plus the count wrapped to two rows that
 * said nothing actionable while the set was legal. So it is the *binding*
 * constraint at rest, which is the smallest cap, and the engines actually
 * exceeded once it is not. Nothing is lost: under the smallest cap you are under
 * all of them, and over one, the only thing worth reading is which.
 */
export function ReferencesGrid({ characterId, rootId, defaultSet, rev, onSaved }: Props) {
  const navigate = useNavigate();
  // Every tile opens into the pool, so scrolling the viewer walks the character's
  // references in the order a shoot would send them.
  const REFS = useMemo(() => ({ in: "refs" as const, id: characterId }), [characterId]);
  const load = useCallback(() => getReferences(characterId), [characterId]);
  const { data, loading, error, reload } = useResource(["references", characterId], load);

  const [tag, setTag] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  /**
   * The set being edited, or `null` when it is only being read.
   *
   * **The set is edited here and one reference at a time nowhere**, because it
   * is written whole: `PATCH /default-set` takes the ordered list and the
   * character's revision, so a per-picture toggle would be a read-modify-write
   * per press. Seeing the whole pool while choosing is also the point — the cap
   * is a fact about the set, not about any member of it.
   */
  const [picking, setPicking] = useState<Set<string> | null>(null);
  const [saving, setSaving] = useState(false);

  const groups = useMemo(() => Object.entries(data?.groups ?? {}), [data]);

  const tags = useMemo(() => {
    const seen = new Set<string>();
    for (const [, entries] of groups) for (const entry of entries) entry.tags.forEach((t) => seen.add(t));
    return [...seen].sort();
  }, [groups]);

  const matches = useCallback(
    (entry: ReferenceEntry) => tag === null || entry.tags.includes(tag),
    [tag],
  );

  /**
   * What a shoot would be shown, as far as this screen can tell.
   *
   * With a tag chosen it is what that tag resolves to — which is exactly what
   * `--pick-tag` means. With none it is the default set, which is what a shoot
   * falls back to. Those are the two things `GET /selection` resolves, and
   * mirroring them is what makes the cap number mean anything.
   */
  /**
   * The members of the default set that are still references.
   *
   * **Counting the ids rather than the entries was a lie this screen told.** A
   * default-set member whose `REF#` row is gone — a re-rendered reference, detached and
   * never re-pointed — is an image a shoot cannot send. The grid said "7" while
   * the shoot sent three, and one character in production carried four of them.
   * Detaching prunes the set now, so this cannot accumulate again; the count
   * stays honest about a library that already has some.
   */
  const staleDefaults = useMemo(() => {
    const attached = new Set(groups.flatMap(([, entries]) => entries.map((e) => e.node)));
    return defaultSet.filter((node) => !attached.has(node));
  }, [defaultSet, groups]);

  /** Every reference in grid order — group order, then position. That IS the shoot order. */
  const ordered = useMemo(
    () => groups.flatMap(([, entries]) => entries.map((entry) => entry.node)),
    [groups],
  );

  const selectionSize = useMemo(() => {
    if (picking) return picking.size;
    if (tag !== null) {
      return groups.reduce((total, [, entries]) => total + entries.filter(matches).length, 0);
    }
    return defaultSet.length - staleDefaults.length;
  }, [defaultSet.length, groups, matches, picking, staleDefaults.length, tag]);

  /**
   * The engines this selection is too big for, and the one that binds first.
   *
   * `ENGINE_CAPS` is ordered smallest-first today and this does not rely on it —
   * a cap added out of order would otherwise change what "the tightest" means
   * without anybody noticing.
   */
  const exceeded = useMemo(
    () => ENGINE_CAPS.filter(({ cap }) => selectionSize > cap),
    [selectionSize],
  );
  const tightest = useMemo(
    () => ENGINE_CAPS.reduce((a, b) => (a.cap <= b.cap ? a : b)),
    [],
  );

  const write = useCallback(
    async (work: Promise<unknown>) => {
      setWriteError(null);
      try {
        await work;
        reload();
      } catch (err) {
        setWriteError((err as Error).message);
      }
    },
    [reload],
  );

  /** The one write this screen makes. Both the drag and the sheet's buttons land here. */
  const place = useCallback(
    (node: string, group: string, after: string | null) =>
      void write(patchReference(characterId, node, { group, ...(after ? { after } : {}) })),
    [characterId, write],
  );

  /**
   * The set, written whole and in grid order.
   *
   * Order matters — it is the order a shoot sends them in — and the grid already
   * shows one: group by group, position by position. So the picked nodes are
   * filtered out of `ordered` rather than kept in click order, which is not
   * information.
   */
  const saveDefaultSet = useCallback(async () => {
    if (!picking) return;
    setSaving(true);
    setWriteError(null);
    try {
      const ack = await setDefaultSet(characterId, ordered.filter((node) => picking.has(node)), rev);
      onSaved(ack);
      setPicking(null);
      reload();
    } catch (err) {
      setWriteError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }, [characterId, onSaved, ordered, picking, reload, rev]);

  const dropOn = useCallback(
    (group: string, after: string | null) => {
      if (dragging === null) return;
      const node = dragging;
      setDragging(null);
      // `after: null` is "put it at the top of this group", which the API reads
      // as the midpoint below the first entry. A regroup and a reorder are the
      // same call — dropping into a different group's strip does both.
      place(node, group, after);
    },
    [dragging, place],
  );


  const attached = useMemo(
    () => new Set(groups.flatMap(([, entries]) => entries.map((entry) => entry.node))),
    [groups],
  );

  if (loading) return <Spinner size="md" label="Loading references" />;

  if (error) {
    return (
      <LoadError what="references" message={error} onRetry={reload} />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/*
        The count, the binding cap, and the tag filter — two rows where there
        were four.

        Not a bordered card any more either: it is the first thing on the panel
        and had a rule under it *and* a border around it, which on a phone is two
        more lines of chrome above the content.
      */}
      <div className="flex flex-col gap-2 border-b border-line pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <Text variant="caption" tone="muted">
            {tag === null ? "Default set" : `Tagged “${tag}”`} ·{" "}
            <span className="tabular-nums">{selectionSize}</span>
          </Text>

          {exceeded.length === 0 ? (
            // The tightest cap, with the headroom left against it. One badge, and
            // it is the only one that can turn.
            <Badge intent="neutral">
              {tightest.engine} {selectionSize}/{tightest.cap}
            </Badge>
          ) : (
            exceeded.map(({ engine, cap }) => (
              <Badge key={engine} intent="danger">
                over {engine} ({cap})
              </Badge>
            ))
          )}

          {staleDefaults.length > 0 && tag === null && !picking && (
            <Badge intent="warning">
              {staleDefaults.length} no longer a reference
            </Badge>
          )}

          <div className="flex-1" />

          {/* **Membership is a deliberate act, not a toggle you pass through.**
              Hard rule #2b treats a character's references as who it IS, so
              choosing the set a shoot falls back to gets its own mode with its
              own save rather than writing on every press. */}
          {picking ? (
            <>
              <Button
                size="sm"
                disabled={saving}
                onClick={() => void saveDefaultSet()}
              >
                {saving ? "Saving…" : "Save default set"}
              </Button>
              <Button
                intent="secondary"
                size="sm"
                disabled={saving}
                onClick={() => setPicking(null)}
              >
                Cancel
              </Button>
            </>
          ) : (
            groups.length > 0 && (
              <Button
                intent="secondary"
                size="sm"
                onClick={() => setPicking(new Set(defaultSet))}
              >
                Edit default set
              </Button>
            )
          )}
        </div>

        {staleDefaults.length > 0 && tag === null && (
          // Named rather than quietly excluded from the count above. The API
          // refuses a default shoot while this is true, so a person seeing the
          // number needs to know why it will not run.
          <Alert.Root intent="warning">
            <Alert.Title>
              {staleDefaults.length} of {defaultSet.length} in the default set are not
              references any more
            </Alert.Title>
            <Alert.Description>
              A shoot that falls back to the default set is refused until they are
              re-pointed — most likely they were re-shot and the replacements were
              never put back in the set. Pick the images that should be in it and
              set it again.
            </Alert.Description>
          </Alert.Root>
        )}

        {tags.length > 0 && (
          // Single-select, and unpressing the pressed one is "no filter" — which
          // is why there is no `All` button beside it. The caption above says
          // which of the two states is showing.
          //
          // Scrolls rather than wraps, in the same row component the folder
          // shortcuts use: a wrapping filter changes the header's *height* as
          // tags come and go, so the grid moves down the screen for reasons that
          // have nothing to do with the grid.
          <ChipRow>
            <ToggleGroup.Root
              aria-label="Filter by tag"
              value={tag === null ? [] : [tag]}
              onValueChange={(next: string[]) => setTag(next[0] ?? null)}
            >
              {tags.map((each) => (
                // Square, like every other chip in the app now. `rounded-none`
                // merges cleanly over the package's own `rounded-md` — this
                // used to be `rounded-full` and it merged the same way. Its
                // `px-md py-sm` is left alone, being a t-shirt key that
                // `tailwind-merge` would keep alongside anything written here.
                <Toggle key={each} value={each} className="shrink-0 rounded-none">
                  {each}
                </Toggle>
              ))}
            </ToggleGroup.Root>
          </ChipRow>
        )}
      </div>

      {writeError && (
        <Alert.Root intent="danger">
          <Alert.Title>That did not work</Alert.Title>
          <Alert.Description>{writeError}</Alert.Description>
        </Alert.Root>
      )}

      {groups.length === 0 ? (
        <Text variant="body" tone="muted">
          No references yet. An image becomes one when somebody says so —
          `studio character add-refs &lt;slug&gt; --to &lt;group&gt;` — never because of the folder it
          sits in.
        </Text>
      ) : (
        groups.map(([group, entries]) => {
          const shown = entries.filter(matches);
          return (
            <section
              key={group}
              className="flex flex-col gap-2"
              onDragOver={(event) => event.preventDefault()}
              // Dropping on the strip rather than on a tile puts the entry at the
              // top of this group, which is also how it is moved *between* groups.
              onDrop={() => dropOn(group, null)}
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <Text variant="title">{group}</Text>
                <Text variant="caption" tone="muted" className="tabular-nums">
                  {shown.length === entries.length
                    ? `${entries.length}`
                    : `${shown.length} of ${entries.length}`}
                </Text>
              </div>

              {/* The same density as the media grid in the browser — two columns
                  of thumbnails on a phone rather than one column of forms. */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
                {shown.map((entry) => (
                  <ReferenceTile
                    key={entry.node}
                    entry={entry}
                    isDefault={
                      picking ? picking.has(entry.node) : (entry.default ?? defaultSet.includes(entry.node))
                    }
                    picking={picking !== null}
                    dragging={dragging === entry.node}
                    onOpen={() =>
                      picking
                        ? setPicking((current) => {
                            const next = new Set(current);
                            if (!next.delete(entry.node)) next.add(entry.node);
                            return next;
                          })
                        : navigate(objectPath(entry.node, REFS))
                    }
                    onDragStart={() => setDragging(entry.node)}
                    onDragEnd={() => setDragging(null)}
                    onDrop={() => dropOn(group, entry.node)}
                  />
                ))}
              </div>
            </section>
          );
        })
      )}

      <Unattached
        rootId={rootId}
        attached={attached}
        groups={groups.map(([name]) => name)}
        onAttach={(node, group) => write(addReference(characterId, { node, group }))}
      />

    </div>
  );
}

/**
 * One reference, as a thumbnail.
 *
 * The whole tile is a `<button>`, which is why nothing inside it may be one — the
 * same constraint every row and tile in this app is under. The drag handlers sit
 * on the wrapper rather than the button so a pointer that has drag keeps it and a
 * finger, which fires none of these, still gets a plain tap.
 */
function ReferenceTile({
  entry,
  isDefault,
  picking,
  dragging,
  onOpen,
  onDragStart,
  onDragEnd,
  onDrop,
}: {
  entry: ReferenceEntry;
  /** In the default set — or, while picking, chosen for it. */
  isDefault: boolean;
  /** The grid is choosing the default set, so a press picks rather than opens. */
  picking: boolean;
  dragging: boolean;
  onOpen: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDrop: () => void;
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        // The section behind this is a drop target too — one that means "top of
        // the group" — so a drop landing on a tile must not also reach it.
        event.stopPropagation();
        onDrop();
      }}
      className={`relative overflow-hidden rounded-none border transition-opacity ${
        dragging ? "border-primary opacity-60" : "border-line"
      }`}
    >
      <button
        type="button"
        onClick={onOpen}
        title={entry.file.name}
        className="block w-full text-left focus-visible:outline-2 focus-visible:outline-offset-[-2px]
                   focus-visible:outline-primary"
      >
        <MediaThumb
          nodeId={entry.node}
          url={entry.file.url}
          name={entry.file.name}
          className="w-full"
        />
        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-gradient-to-t
                     from-neutral-1/85 to-transparent px-1.5 pb-1 pt-4 font-mono text-xs text-neutral-12"
        >
          {entry.file.name}
        </span>
      </button>

      {/* A marker while reading, a tick while choosing. Membership is still not
          something a stray press can change — picking is a mode with its own
          save, which is what hard rule #2b asks of an identity decision. */}
      {picking ? (
        <span
          className={`pointer-events-none absolute left-1.5 top-1.5 flex size-6 items-center
                      justify-center rounded-none border ${
                        isDefault
                          ? "border-primary bg-primary text-primary-text"
                          : "border-neutral-a11 bg-neutral-1/85"
                      }`}
        >
          {isDefault && <CheckIcon className="size-4 fill-none stroke-current stroke-[3]" />}
        </span>
      ) : (
        isDefault && (
          <span className="pointer-events-none absolute left-1.5 top-1.5">
            <Badge intent="success">default</Badge>
          </span>
        )
      )}
    </div>
  );
}

/*
 * `ReferenceSheet` was here — a bottom sheet holding a 256px-tall image and the
 * fields beside it.
 *
 * A reference pool is judged by LOOKING, and nobody can tell whether a face is
 * on-model from a thumbnail with a form under it. The picture fills the screen
 * now (`/o/<node>?in=refs:<char>`) and the fields moved into the viewer's own
 * panel — see `ReferenceFields`. Regrouping and reordering send the same
 * `{group, after}` they always did; the drag on the tiles is untouched and is
 * still the accelerator for pointers that have one.
 */

/**
 * Images sitting in `reference/` that no `REF#` row claims.
 *
 * **This is what the second tab was for.** The character page used to show a
 * `References` tab beside a `reference` one — the row index and the folder — on
 * the reasoning that an image is identity because a row says so and not because
 * of where it sits, so the two can disagree. That is true, and two adjacent tabs
 * differing by a capital letter is the worst way to say it: the reader had to
 * diff two listings by eye to find the case worth seeing.
 *
 * So the disagreement is stated. Nothing here writes — attaching a reference is a
 * decision about identity, hard rule #2b, and `studio character add-refs` is
 * where it is made.
 *
 * The folder is found by name, and its absence is ordinary: `reference/` is a
 * convention the entity model deliberately stopped enforcing, so a character
 * without one simply has no unattached pool to report.
 */
function Unattached({
  rootId,
  attached,
  groups,
  onAttach,
}: {
  rootId: string;
  attached: ReadonlySet<string>;
  /** Where an image can be attached. Empty until the pool has its first group. */
  groups: string[];
  onAttach: (node: string, group: string) => void;
}) {
  const load = useCallback(async () => {
    const root = await getTree({ node: rootId }, "name");
    const folder = root.folders.find((each) => each.name === REFERENCE_FOLDER);
    if (!folder) return [] as FileEntry[];
    const listing = await getTree({ node: folder.id }, "name");
    return listing.files.filter((file) => file.kind === "image");
  }, [rootId]);

  const { data } = useResource(["unattached", rootId], load);
  const [target, setTarget] = useState(groups[0] ?? "");

  const loose = useMemo(
    () => (data ?? []).filter((file) => !attached.has(file.id)),
    [attached, data],
  );

  if (loose.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <Text variant="title">In {REFERENCE_FOLDER}/, not attached</Text>
        <Text variant="caption" tone="muted" className="tabular-nums">
          {loose.length}
        </Text>
      </div>
      {/* **The copy used to send you to the CLI, and now the button is here.**
          The rule it was quoting is unchanged: an image becomes identity when
          somebody says so, never because of the folder it sits in. What changed
          is only where "somebody says so" can happen — the press still arms and
          names the group before it commits. */}
      <Text variant="caption" tone="muted">
        These are files in the folder, not references. An image becomes one when somebody says so
        {groups.length === 0 && " — this character has no groups yet, so `studio character add-refs` makes the first"}
        .
      </Text>

      {groups.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Text variant="caption" tone="muted">
            Add to
          </Text>
          <Select
            aria-label="Group to add to"
            options={groups.map((name) => ({ value: name, label: name }))}
            value={target}
            onValueChange={setTarget}
          />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {loose.map((file) => (
          <div
            key={file.id}
            className="relative overflow-hidden rounded-none border border-dashed border-line"
          >
            <MediaThumb
              nodeId={file.id}
              url={file.url}
              name={file.name}
              title={file.name}
              className="w-full"
              mediaClassName="opacity-70"
            />
            {groups.length > 0 && (
              <AttachButton name={file.name} group={target} onAttach={() => onAttach(file.id, target)} />
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * Attach one image, in two presses.
 *
 * **Armed rather than immediate, and the armed label names the group.** Hard
 * rule #2b makes this a decision about who the character IS — separate from
 * having agreed to spend money rendering the picture — so it gets the same
 * two-press shape every consequential control in this app uses. The difference
 * from a delete is only which way it goes.
 */
function AttachButton({
  name,
  group,
  onAttach,
}: {
  name: string;
  group: string;
  onAttach: () => void;
}) {
  const [armed, setArmed] = useState(false);

  return (
    <button
      type="button"
      aria-label={armed ? `Confirm — add ${name} to ${group}` : `Add ${name} as a reference`}
      title={armed ? `Confirm — add to ${group}` : "Add as a reference"}
      onClick={() => (armed ? onAttach() : setArmed(true))}
      onBlur={() => setArmed(false)}
      className={`absolute inset-x-1 bottom-1 rounded-none px-2 py-1 font-body text-xs transition-colors
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                  ${armed ? "bg-primary text-primary-text" : "bg-neutral-1/80 text-neutral-12 hover:bg-neutral-1/95"}`}
    >
      {armed ? `Add to ${group}?` : "Add as reference"}
    </button>
  );
}
