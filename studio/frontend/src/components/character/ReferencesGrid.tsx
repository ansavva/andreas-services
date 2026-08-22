import { useCallback, useMemo, useState } from "react";

import { Alert, Badge, Button, Spinner, Text, Textarea } from "@ansavva/design-system";

import { getReferences, patchReference } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { ENGINE_CAPS, type ReferenceEntry } from "../../types";

interface Props {
  characterId: string;
  /** Marked on the grid. Held on the record because it is small, ordered and read on every shoot. */
  defaultSet: string[];
}

/**
 * The reference pool: grouped, ordered, described, and reorderable by dragging.
 *
 * **Every one of those was a filename before.** `<slug>_<group>_<n>.png` carried
 * the group and the position, the bible's `references:` map carried the
 * description keyed on that same basename, and the two went out of step every
 * time either was renumbered. Group and order are attributes on a row now, so
 * regrouping copies no bytes, reordering is one write that touches neither
 * neighbour, and a description is a row's own field rather than a rewrite of the
 * whole bible.
 *
 * ## Reordering writes `after`, never an index
 *
 * `order` is gapped by 1000 and a drop sends `{after: <node>}`, which the API
 * turns into the midpoint of that entry's order and the next one's. Sending a
 * position would make every reorder a rewrite of the whole group and would race
 * with anybody else's; a midpoint is one conditional write.
 *
 * ## The caps are a warning, not the check
 *
 * `GET /api/characters/<id>/selection` is what actually refuses an over-cap set,
 * with the index in the body, and it does so before any money is spent. What is
 * drawn here is the same arithmetic done early, so the refusal is visible while
 * the set is being built rather than at the point of a shoot. If an engine's cap
 * moves this warns slightly early or slightly late; it can never let one through.
 */
export function ReferencesGrid({ characterId, defaultSet }: Props) {
  const load = useCallback(() => getReferences(characterId), [characterId]);
  const { data, loading, error, reload } = useResource(load);

  const [tag, setTag] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);

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

  const dropOn = useCallback(
    (group: string, after: string | null) => {
      if (dragging === null) return;
      const node = dragging;
      setDragging(null);
      // `after: null` is "put it at the top of this group", which the API reads
      // as the midpoint below the first entry. A regroup and a reorder are the
      // same call — dropping into a different group's strip does both.
      void write(patchReference(characterId, node, { group, ...(after ? { after } : {}) }));
    },
    [characterId, dragging, write],
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

  if (groups.length === 0) {
    return (
      <Text variant="body" tone="muted">
        No references yet. An image becomes one when somebody says so —
        `studio character add-refs &lt;slug&gt; --to &lt;group&gt;` — never because of the folder it
        sits in.
      </Text>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-card px-3 py-2">
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

        <div className="flex-1" />

        <Button intent={tag === null ? "primary" : "ghost"} size="sm" onClick={() => setTag(null)}>
          All
        </Button>
        {tags.map((each) => (
          <Button
            key={each}
            intent={tag === each ? "primary" : "ghost"}
            size="sm"
            onClick={() => setTag(tag === each ? null : each)}
          >
            {each}
          </Button>
        ))}
      </div>

      {writeError && (
        <Alert.Root intent="danger">
          <Alert.Title>That did not work</Alert.Title>
          <Alert.Description>{writeError}</Alert.Description>
        </Alert.Root>
      )}

      {groups.map(([group, entries]) => {
        const shown = entries.filter(matches);
        return (
          <section
            key={group}
            className="flex flex-col gap-2"
            onDragOver={(event) => event.preventDefault()}
            // Dropping on the strip rather than on a card puts the entry at the
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

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((entry) => (
                <ReferenceCard
                  key={entry.node}
                  entry={entry}
                  isDefault={entry.default ?? defaultSet.includes(entry.node)}
                  dragging={dragging === entry.node}
                  onDragStart={() => setDragging(entry.node)}
                  onDragEnd={() => setDragging(null)}
                  onDrop={() => dropOn(group, entry.node)}
                  onDescribe={(description) =>
                    write(patchReference(characterId, entry.node, { description }))
                  }
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function ReferenceCard({
  entry,
  isDefault,
  dragging,
  onDragStart,
  onDragEnd,
  onDrop,
  onDescribe,
}: {
  entry: ReferenceEntry;
  isDefault: boolean;
  dragging: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDrop: () => void;
  onDescribe: (description: string) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState(entry.description);

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        // The section behind this is a drop target too — one that means "top of
        // the group" — so a drop landing on a card must not also reach it.
        event.stopPropagation();
        onDrop();
      }}
      className={`flex flex-col gap-2 rounded-md border bg-card p-2 ${
        dragging ? "border-primary opacity-60" : "border-line"
      }`}
    >
      <div className="flex items-start gap-2">
        <img
          src={entry.file.url}
          alt={entry.file.name}
          className="size-20 shrink-0 rounded-md border border-line object-cover"
        />
        <div className="min-w-0 flex-1">
          <Text variant="body" className="truncate">
            {entry.file.name}
          </Text>
          <Text variant="caption" tone="muted" className="tabular-nums">
            order {entry.order}
          </Text>
          <div className="flex flex-wrap items-center gap-1 pt-1">
            {/* A marker, not a control. Membership of the default set is a
                decision about identity — hard rule #2b — and this grid is where
                it is *read*, not where it is made. */}
            {isDefault && <Badge intent="success">default set</Badge>}
            {entry.tags.map((each) => (
              <Badge key={each} intent="neutral">
                {each}
              </Badge>
            ))}
          </div>
        </div>
      </div>

      {/* Saved on blur rather than per keystroke: one row write per description
          written, not one per character, and the field is the only feedback
          anybody needs that it took. */}
      <Textarea
        value={draft}
        rows={2}
        aria-label={`Description of ${entry.file.name}`}
        placeholder="What this reference shows"
        onValueChange={setDraft}
        onBlur={() => {
          if (draft !== entry.description) void onDescribe(draft);
        }}
      />
    </div>
  );
}
