import { useCallback, useEffect, useState } from "react";

import { Alert, Breadcrumbs, Button, Dialog, Text } from "@ansavva/design-system";

import { ApertureSpinner } from "../common/Aperture";
import { getTree } from "../../apis/studio";
import type { Crumb, FolderEntry } from "../../types";
import type { FolderId } from "../../utils/location";
import { ArrowUpIcon, FolderIcon } from "../common/icons";

interface Props {
  /** Which operation this is picking a destination for. */
  verb: "move" | "copy";
  /** What is being moved or copied, written into the title — "3 files", "seed". */
  noun: string;
  /** Where the picker opens. Normally the folder being moved out of. */
  startId: FolderId;
  /**
   * The folder the items are already in.
   *
   * Only meaningful for a move, where picking it is a no-op. A *copy* into the
   * folder you are looking at is a real operation — it is how a file is
   * duplicated, and the server numbers the second one — so it stays enabled.
   */
  currentId: FolderId;
  /**
   * A folder the destination may not be — set when moving a *folder*, to its own
   * id.
   *
   * Fencing the folder itself fences its whole subtree, because it is the only
   * way into one: the picker descends by clicking, and this row cannot be
   * clicked. The API refuses the move too; disabling it here is so the row
   * explains itself instead of the request coming back as an error.
   */
  forbiddenId?: string;
  onSubmit: (destination: string) => Promise<unknown>;
  onClose: () => void;
}

/**
 * Pick a destination folder by browsing to it, for a move or for a copy.
 *
 * A typed address was the obvious alternative and is worse: the whole point of a
 * move is that you are looking at a library whose folder names are timestamps,
 * and nobody types a run folder's name correctly. So this walks the same
 * `/api/tree` the page behind it does, showing folders only — the files in a
 * destination are not a thing you are choosing between.
 *
 * **It browses and submits node ids**, which is the one thing that changed here
 * in the entity rework. It used to hand back a *prefix*, because the write routes
 * took a name path; `POST /api/nodes/move` and `/copy` take an id, and browsing
 * by the same address they accept means nothing has to translate between the two.
 *
 * It is a `Dialog`, which portals to `<body>` — and that used to be the whole
 * reason there was no move or copy button on the viewer, which was often inside
 * a fullscreen element where a body portal is not painted. `Dialog.Root` takes
 * a `container` as of design system 0.16.0, so that is a choice now rather than
 * a wall: this picker would work over a fullscreen player if it were handed the
 * player's element. It is still only wired to the browse page, because moving a
 * file is something you do to a listing.
 */
export function DestinationPicker({
  verb,
  noun,
  startId,
  currentId,
  forbiddenId,
  onSubmit,
  onClose,
}: Props) {
  const [folderId, setFolderId] = useState<FolderId>(startId);
  const [folders, setFolders] = useState<FolderEntry[]>([]);
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    // Always by name: this is a folder chooser, and "newest first" is an answer
    // to a question nobody asks while looking for somewhere to put something.
    getTree(folderId === null ? {} : { node: folderId }, "name")
      .then((result) => {
        if (cancelled) return;
        setFolders(result.folders);
        setCrumbs(result.breadcrumbs);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [folderId]);

  // Up, and whether there is an up, come from the trail the listing returned.
  // The server built that trail by walking `parent_id`, so it is the tree's own
  // answer rather than a second, guessing implementation of it.
  const parent = crumbs.at(-2)?.id;
  /** The chosen folder as a real node — the root has one, and `folderId` is null there. */
  const destination = crumbs.at(-1)?.id ?? null;
  const shownPath = crumbs.at(-1)?.prefix ?? "";

  const inForbidden = forbiddenId !== undefined && crumbs.some((crumb) => crumb.id === forbiddenId);
  // A move into the folder the items are already in does nothing; a copy into it
  // duplicates them, which is a thing people want.
  const isNoOp = verb === "move" && destination !== null && destination === currentId;
  const canSubmit = !loading && !inForbidden && !isNoOp && destination !== null;

  const submit = useCallback(() => {
    if (destination === null) return;
    setBusy(true);
    setError(null);
    onSubmit(destination)
      .then(() => onClose())
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, [destination, onClose, onSubmit]);

  return (
    <Dialog.Root open onOpenChange={(next: boolean) => !next && onClose()}>
      <Dialog.Backdrop />
      <Dialog.Popup className="flex max-h-[80vh] w-full max-w-lg flex-col gap-3 p-4">
        <Dialog.Title>
          {verb === "move" ? "Move" : "Copy"} {noun}
        </Dialog.Title>

        <Breadcrumbs.Root>
          {crumbs.map((crumb, index, all) => (
            <Breadcrumbs.Item
              key={crumb.id}
              current={index === all.length - 1}
              href="#"
              onClick={(event: React.MouseEvent) => {
                event.preventDefault();
                setFolderId(crumb.id);
              }}
            >
              {crumb.name}
            </Breadcrumbs.Item>
          ))}
        </Breadcrumbs.Root>

        <div className="min-h-40 flex-1 overflow-auto rounded-md border border-line">
          {loading && (
            <div className="flex h-40 items-center justify-center">
              <ApertureSpinner size="md" label="Loading folders" />
            </div>
          )}

          {!loading && (
            <div className="flex flex-col">
              {parent !== undefined && (
                <PickerRow up onSelect={() => setFolderId(parent)}>
                  Up one folder
                </PickerRow>
              )}

              {folders.map((folder) => (
                <PickerRow
                  key={folder.id}
                  // The folder being moved cannot be its own destination, and
                  // showing it greyed says why better than hiding it does.
                  disabled={folder.id === forbiddenId}
                  onSelect={() => setFolderId(folder.id)}
                >
                  {folder.name}
                </PickerRow>
              ))}

              {folders.length === 0 && (
                <Text variant="caption" tone="muted" className="p-3">
                  No folders here — {verb === "move" ? "moving" : "copying"} into this one is
                  still fine.
                </Text>
              )}
            </div>
          )}
        </div>

        {/* The *path* is what is shown, because a node id names nothing a person
            recognises. What is submitted is the id beside it. */}
        <Text variant="caption" tone="muted" className="truncate">
          Destination: {shownPath || "/"}
        </Text>

        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>That did not work</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        <div className="flex items-center justify-end gap-2">
          <Button intent="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          {/* Disabled rather than absent, with the reason on the label: a button
              that vanishes when you navigate somewhere it cannot be used reads as
              a bug, not as an explanation. */}
          <Button size="sm" disabled={!canSubmit || busy} onClick={submit}>
            {busy
              ? verb === "move"
                ? "Moving…"
                : "Copying…"
              : isNoOp
                ? "Already here"
                : inForbidden
                  ? "Not in itself"
                  : verb === "move"
                    ? "Move here"
                    : "Copy here"}
          </Button>
        </div>
      </Dialog.Popup>
    </Dialog.Root>
  );
}

function PickerRow({
  children,
  onSelect,
  disabled = false,
  up = false,
}: {
  children: React.ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  up?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      className="flex items-center gap-2 border-b border-line px-3 py-2.5 text-left last:border-b-0
                 transition-colors hover:bg-surface-alt disabled:cursor-default disabled:opacity-40
                 disabled:hover:bg-transparent
                 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
    >
      {up ? <ArrowUpIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" /> : <FolderIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" />}
      <Text variant="body" className="truncate">
        {children}
      </Text>
    </button>
  );
}
