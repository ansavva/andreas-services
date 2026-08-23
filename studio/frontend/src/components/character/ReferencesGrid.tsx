import { useCallback, useMemo, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Drawer,
  Select,
  Separator,
  Spinner,
  Text,
  Textarea,
  Toggle,
  ToggleGroup,
} from "@ansavva/design-system";

import { getReferences, getTree, patchReference } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { ENGINE_CAPS, type FileEntry, type ReferenceEntry } from "../../types";

interface Props {
  characterId: string;
  /** The character's root node — where the `reference/` folder is looked for. */
  rootId: string;
  /** Marked on the grid. Held on the record because it is small, ordered and read on every shoot. */
  defaultSet: string[];
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
 */
export function ReferencesGrid({ characterId, rootId, defaultSet }: Props) {
  const load = useCallback(() => getReferences(characterId), [characterId]);
  const { data, loading, error, reload } = useResource(load);

  const [tag, setTag] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [openNode, setOpenNode] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);

  const groups = useMemo(() => Object.entries(data?.groups ?? {}), [data]);
  const groupNames = useMemo(() => groups.map(([name]) => name), [groups]);

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
  const selectionSize = useMemo(() => {
    if (tag !== null) {
      return groups.reduce((total, [, entries]) => total + entries.filter(matches).length, 0);
    }
    return defaultSet.length;
  }, [defaultSet.length, groups, matches, tag]);

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

  /**
   * Move one place within a group, which is the touch path for what a drag does.
   *
   * The API places an entry *after* another one, so a step up lands after the
   * entry two above it — or at the top of the group, which is what a null anchor
   * means. A step down lands after its next neighbour. Both are the same single
   * conditional write a drop makes.
   */
  const nudge = useCallback(
    (entry: ReferenceEntry, group: string, delta: -1 | 1) => {
      const entries = data?.groups[group] ?? [];
      const at = entries.findIndex((each) => each.node === entry.node);
      const to = at + delta;
      if (at < 0 || to < 0 || to >= entries.length) return;
      const anchor = delta === -1 ? (entries[at - 2]?.node ?? null) : (entries[at + 1]?.node ?? null);
      place(entry.node, group, anchor);
    },
    [data, place],
  );

  /** The open entry, re-read from the listing so a write refreshes the sheet under it. */
  const open = useMemo(() => {
    if (openNode === null) return null;
    for (const [group, entries] of groups) {
      const at = entries.findIndex((entry) => entry.node === openNode);
      if (at >= 0) return { entry: entries[at]!, group, index: at, total: entries.length };
    }
    return null;
  }, [groups, openNode]);

  const attached = useMemo(
    () => new Set(groups.flatMap(([, entries]) => entries.map((entry) => entry.node))),
    [groups],
  );

  if (loading) return <Spinner size="md" label="Loading references" />;

  if (error) {
    return (
      <Alert.Root intent="danger">
        <Alert.Title>Could not load references</Alert.Title>
        <Alert.Description>{error}</Alert.Description>
      </Alert.Root>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/*
        The count, the caps and the tag filter.

        Not a bordered card any more — it is the first thing on the panel and had
        a rule under it and a border around it, which on a phone is two lines of
        chrome above the content.
      */}
      <div className="flex flex-col gap-2 border-b border-line pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <Text variant="caption" tone="muted">
            {tag === null ? "Default set" : `Tagged “${tag}”`}:{" "}
            <span className="tabular-nums">{selectionSize}</span>
          </Text>

          {/* One badge per engine, so an over-cap set is a colour rather than a
              number somebody has to compare in their head. */}
          {ENGINE_CAPS.map(({ engine, cap }) => (
            <Badge key={engine} intent={selectionSize > cap ? "danger" : "neutral"}>
              {engine} {selectionSize}/{cap}
            </Badge>
          ))}
        </div>

        {tags.length > 0 && (
          // Single-select, and unpressing the pressed one is "no filter" — which
          // is why there is no `All` button beside it any more. The caption above
          // says which of the two states is showing.
          <ToggleGroup.Root
            aria-label="Filter by tag"
            value={tag === null ? [] : [tag]}
            onValueChange={(next: string[]) => setTag(next[0] ?? null)}
            className="flex-wrap"
          >
            {tags.map((each) => (
              <Toggle key={each} value={each}>
                {each}
              </Toggle>
            ))}
          </ToggleGroup.Root>
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
                    isDefault={entry.default ?? defaultSet.includes(entry.node)}
                    dragging={dragging === entry.node}
                    onOpen={() => setOpenNode(entry.node)}
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

      <Unattached rootId={rootId} attached={attached} />

      {open && (
        <ReferenceSheet
          // The sheet holds a description draft. Keyed on the node so it cannot
          // outlive the entry it was typed against — a move or a regroup keeps
          // the same instance, which is wanted, and a different reference does
          // not.
          key={open.entry.node}
          entry={open.entry}
          group={open.group}
          groups={groupNames}
          index={open.index}
          total={open.total}
          isDefault={open.entry.default ?? defaultSet.includes(open.entry.node)}
          onClose={() => setOpenNode(null)}
          onRegroup={(next) => place(open.entry.node, next, null)}
          onNudge={(delta) => nudge(open.entry, open.group, delta)}
          onDescribe={(description) =>
            write(patchReference(characterId, open.entry.node, { description }))
          }
        />
      )}
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
  dragging,
  onOpen,
  onDragStart,
  onDragEnd,
  onDrop,
}: {
  entry: ReferenceEntry;
  isDefault: boolean;
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
      className={`relative overflow-hidden rounded-md border transition-opacity ${
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
        <img
          src={entry.file.url}
          alt={entry.file.name}
          className="aspect-square w-full bg-surface-alt object-cover"
        />
        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-gradient-to-t
                     from-black/80 to-transparent px-1.5 pb-1 pt-4 font-body text-xs text-white"
        >
          {entry.file.name}
        </span>
      </button>

      {/* A marker, not a control. Membership of the default set is a decision
          about identity — hard rule #2b — and this grid is where it is *read*,
          not where it is made. */}
      {isDefault && (
        <span className="pointer-events-none absolute left-1.5 top-1.5">
          <Badge intent="success">default</Badge>
        </span>
      )}
    </div>
  );
}

/**
 * One reference's fields, and the two controls that move it.
 *
 * A bottom sheet on a phone and a right-hand panel from `lg` up, which is one
 * `Drawer` and a handful of `lg:` classes rather than two components: the
 * geometry is the only thing that differs, and `Drawer.Panel` merges what it is
 * given over its own side styles.
 */
function ReferenceSheet({
  entry,
  group,
  groups,
  index,
  total,
  isDefault,
  onClose,
  onRegroup,
  onNudge,
  onDescribe,
}: {
  entry: ReferenceEntry;
  group: string;
  groups: string[];
  index: number;
  total: number;
  isDefault: boolean;
  onClose: () => void;
  onRegroup: (group: string) => void;
  onNudge: (delta: -1 | 1) => void;
  onDescribe: (description: string) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState(entry.description);

  return (
    <Drawer.Root open onOpenChange={(next) => !next && onClose()} side="bottom">
      <Drawer.Backdrop />
      <Drawer.Panel
        className="max-h-[85vh] rounded-t-lg
                   lg:inset-y-0 lg:left-auto lg:right-0 lg:h-full lg:max-h-none lg:w-full
                   lg:max-w-md lg:rounded-none lg:border-l lg:border-t-0"
      >
        {/* A direct child of the panel, and it has to be: `Drawer.Panel` decides
            whether to set `aria-labelledby` by looking for a `Drawer.Title`
            among its own children, so a title wrapped in a header row of my own
            leaves the dialog unnamed. Which is why the close is at the foot
            rather than opposite it — that, plus the backdrop and Escape, which
            both dismiss. */}
        <Drawer.Title className="min-w-0 truncate">{entry.file.name}</Drawer.Title>

        <img
          src={entry.file.url}
          alt={entry.file.name}
          className="max-h-64 w-full rounded-md border border-line bg-surface-alt object-contain
                     lg:max-h-72"
        />

        <div className="flex flex-wrap items-center gap-1">
          {isDefault && <Badge intent="success">default set</Badge>}
          {entry.tags.map((each) => (
            <Badge key={each} intent="neutral">
              {each}
            </Badge>
          ))}
        </div>

        <Separator />

        {/* Regrouping and reordering, on every pointer. These send the same
            `{group, after}` a drop does — see `place` and `nudge`. */}
        <div className="flex flex-col gap-2">
          <Text variant="caption" tone="muted">
            Group
          </Text>
          <Select
            aria-label="Group"
            options={groups.map((name) => ({ value: name, label: name }))}
            value={group}
            onValueChange={(next: string) => {
              if (next !== group) onRegroup(next);
            }}
          />
        </div>

        <div className="flex items-center gap-2">
          <Text variant="caption" tone="muted" className="tabular-nums">
            {index + 1} of {total}
          </Text>
          <div className="flex-1" />
          <Button intent="ghost" size="sm" disabled={index === 0} onClick={() => onNudge(-1)}>
            <span aria-hidden="true">↑</span> Up
          </Button>
          <Button
            intent="ghost"
            size="sm"
            disabled={index === total - 1}
            onClick={() => onNudge(1)}
          >
            <span aria-hidden="true">↓</span> Down
          </Button>
        </div>

        <Separator />

        {/* Saved on blur rather than per keystroke: one row write per description
            written, not one per character. */}
        <div className="flex flex-col gap-2">
          <Text variant="caption" tone="muted">
            Description
          </Text>
          <Textarea
            value={draft}
            rows={4}
            aria-label={`Description of ${entry.file.name}`}
            placeholder="What this reference shows"
            onValueChange={setDraft}
            onBlur={() => {
              if (draft !== entry.description) void onDescribe(draft);
            }}
          />
        </div>

        {/* Full width and at the foot, where a thumb reaches it on a phone. The
            description saves on blur, so leaving by this button commits it. */}
        <Drawer.Close className="mt-auto w-full self-stretch rounded-md border border-line py-2 text-center">
          Done
        </Drawer.Close>
      </Drawer.Panel>
    </Drawer.Root>
  );
}

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
function Unattached({ rootId, attached }: { rootId: string; attached: ReadonlySet<string> }) {
  const load = useCallback(async () => {
    const root = await getTree({ node: rootId }, "name");
    const folder = root.folders.find((each) => each.name === REFERENCE_FOLDER);
    if (!folder) return [] as FileEntry[];
    const listing = await getTree({ node: folder.id }, "name");
    return listing.files.filter((file) => file.kind === "image");
  }, [rootId]);

  const { data } = useResource(load);

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
      <Text variant="caption" tone="muted">
        These are files in the folder, not references. An image becomes one when somebody says so —
        `studio character add-refs &lt;slug&gt; --to &lt;group&gt;`.
      </Text>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {loose.map((file) => (
          <div key={file.id} className="overflow-hidden rounded-md border border-dashed border-line">
            <img
              src={file.url}
              alt={file.name}
              title={file.name}
              className="aspect-square w-full bg-surface-alt object-cover opacity-70"
            />
          </div>
        ))}
      </div>
    </section>
  );
}
