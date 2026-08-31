import { useCallback, useMemo, useState } from "react";

import { Badge, Button, Select, Separator, Text } from "@ansavva/design-system";

import { deleteReference, getReferences, patchReference } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { AutoTextarea } from "../common/AutoTextarea";
import { ConfirmDeleteButton } from "../common/ConfirmDeleteButton";

interface Props {
  characterId: string;
  /** The node open in the viewer. Not every one of them is a reference. */
  node: string;
  /** Called after a write that changes the pool, so the sequence behind can re-read. */
  onChanged: () => void;
}

/**
 * What a picture is to a CHARACTER, edited where you are looking at it.
 *
 * **This replaces the reference sheet.** A `Drawer` used to open on tap holding
 * a 256px-tall image and these fields, which is exactly the wrong shape for the
 * job: a reference pool is judged by *looking*, and no one can tell whether a
 * face is on-model from a thumbnail with a form under it. The picture fills the
 * screen now and the fields sit in the panel that already exists for saying what
 * a frame shows.
 *
 * ## Two descriptions, and they are genuinely different things
 *
 * The panel below this one writes `description` onto the **file** (#483) — what
 * the picture shows, travelling with it through a move or a copy. This one
 * writes the description on the **`REF#` row**, which is what the described
 * reference index is built from when a subset of a large pool is chosen for a
 * shoot. The same image can be a reference for one character and a plain file
 * everywhere else, so the two cannot be one field. They are labelled apart
 * rather than merged.
 *
 * ## What is not here
 *
 * **Default-set membership is read-only on this screen.** It is a decision about
 * a *set* — an ordered list written whole, against the character's revision —
 * so editing it one picture at a time from a viewer would be a read-modify-write
 * per press against a record this screen does not hold. The grid owns it, where
 * the whole set is visible at once. Hard rule #2b is the other half of that: it
 * is an identity decision and should be made deliberately, not toggled in
 * passing while scrolling.
 */
export function ReferenceFields({ characterId, node, onChanged }: Props) {
  const load = useCallback(() => getReferences(characterId), [characterId]);
  const { data, loading, reload } = useResource(["references", characterId], load);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const groups = useMemo(() => Object.entries(data?.groups ?? {}), [data]);
  const groupNames = useMemo(() => groups.map(([name]) => name), [groups]);

  /** Where this node sits, or `null` when it is a file that no `REF#` row claims. */
  const found = useMemo(() => {
    for (const [group, entries] of groups) {
      const at = entries.findIndex((entry) => entry.node === node);
      if (at >= 0) return { entry: entries[at]!, group, index: at, entries };
    }
    return null;
  }, [groups, node]);

  const [draft, setDraft] = useState<string | null>(null);

  const write = useCallback(
    async (work: Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await work;
        reload();
        onChanged();
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [onChanged, reload],
  );

  if (loading || !found) {
    // Not a reference — an ordinary file in the pool's folder, or the listing
    // has not landed. Either way there is nothing character-shaped to say about
    // it, and an empty section with a heading would imply otherwise.
    return null;
  }

  const { entry, group, index, entries } = found;
  const caption = draft ?? entry.description;

  /**
   * One step within the group, which is the same single write a drag makes.
   *
   * The API places an entry *after* another one, so a step up lands after the
   * entry two above it — or at the top of the group, which is what a null
   * anchor means.
   */
  const nudge = (delta: -1 | 1) => {
    const to = index + delta;
    if (to < 0 || to >= entries.length) return;
    const anchor = delta === -1 ? (entries[index - 2]?.node ?? null) : (entries[index + 1]?.node ?? null);
    void write(patchReference(characterId, node, { group, ...(anchor ? { after: anchor } : {}) }));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Text variant="caption" tone="muted">
          Reference
        </Text>
        {(entry.default ?? false) && <Badge intent="success">default set</Badge>}
        {entry.tags.map((each) => (
          <Badge key={each} intent="neutral">
            {each}
          </Badge>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex flex-col gap-1">
          <Text variant="caption" tone="muted">
            Group
          </Text>
          <Select
            aria-label="Group"
            options={groupNames.map((name) => ({ value: name, label: name }))}
            value={group}
            disabled={busy}
            onValueChange={(next: string) => {
              // A regroup lands at the top of the group it moves into, which is
              // the same thing dropping onto a group's strip has always meant.
              if (next !== group) void write(patchReference(characterId, node, { group: next }));
            }}
          />
        </div>

        <div className="flex flex-col gap-1">
          <Text variant="caption" tone="muted">
            Position
          </Text>
          <div className="flex items-center gap-2">
            <Text variant="caption" tone="muted" className="tabular-nums font-mono">
              {index + 1} of {entries.length}
            </Text>
            <Button intent="secondary" size="sm" disabled={busy || index === 0} onClick={() => nudge(-1)}>
              <span aria-hidden="true">↑</span> Up
            </Button>
            <Button
              intent="secondary"
              size="sm"
              disabled={busy || index === entries.length - 1}
              onClick={() => nudge(1)}
            >
              <span aria-hidden="true">↓</span> Down
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Text variant="caption" tone="muted">
          Caption — what a shoot is told this reference shows
        </Text>
        <AutoTextarea
          value={caption}
          aria-label="Reference caption"
          placeholder="Three-quarter left, neutral expression, flat light."
          onValueChange={setDraft}
          // Same rule as the description below: an explicit press, never blur.
          // This panel closes on Escape, and blur-to-save is how an edit gets
          // committed by the gesture meant to abandon it.
          onKeyDown={(event: React.KeyboardEvent) => event.stopPropagation()}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            disabled={busy || draft === null || draft === entry.description}
            onClick={() => {
              void write(patchReference(characterId, node, { description: caption.trim() }));
              setDraft(null);
            }}
          >
            {busy ? "Saving…" : "Save caption"}
          </Button>
          {draft !== null && draft !== entry.description && (
            <Button intent="secondary" size="sm" onClick={() => setDraft(null)}>
              Discard
            </Button>
          )}

          <div className="flex-1" />

          {/* Detaching drops the `REF#` row and leaves the file exactly where it
              is — this picture stops being part of who the character is, and
              nothing is deleted. The armed label says so. */}
          <ConfirmDeleteButton
            tone="chrome"
            noun="this reference — the file stays"
            onConfirm={() => write(deleteReference(characterId, node))}
          />
        </div>
      </div>

      {error && (
        <Text variant="caption" className="text-danger">
          {error}
        </Text>
      )}

      <Separator />
    </div>
  );
}
