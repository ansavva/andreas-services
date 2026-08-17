import { useCallback, useEffect, useState } from "react";

import { Alert, Breadcrumbs, Button, Dialog, Spinner, Text } from "@ansavva/design-system";

import { getTree } from "../../apis/studio";
import type { Crumb, FolderEntry } from "../../types";
import { ROOT_PREFIX, parentPrefix } from "../../utils/location";

interface Props {
  /** What is being moved, written into the title — "3 files", "seed". */
  noun: string;
  /** Where the picker opens. Normally the folder being moved out of. */
  startPrefix: string;
  /**
   * A subtree the destination may not be inside — set when moving a *folder*, to
   * its own prefix. The API refuses this too; disabling it here is so the button
   * explains itself instead of the request coming back as an error.
   */
  forbiddenPrefix?: string;
  /** The folder the items are already in. Picking it is a no-op, so it is not offered. */
  currentPrefix: string;
  onMove: (destination: string) => Promise<unknown>;
  onClose: () => void;
}

/**
 * Pick a destination folder by browsing to it.
 *
 * A typed prefix was the obvious alternative and is worse: the whole point of a
 * move is that you are looking at a library whose folder names are timestamps,
 * and nobody types `projects/<project>/scenes/2026-08-16_07-40-22_stadium-encounter/`
 * correctly. So this walks the same `/api/tree` the page behind it does, showing
 * folders only — the files in a destination are not a thing you are choosing
 * between.
 *
 * It is a `Dialog`, which portals to `<body>`, and that is safe *here*
 * specifically: moving is a browse-page action and the browse page is never
 * inside a fullscreen element. The reel's controls stay inline for the reason
 * `ConfirmDeleteButton` documents, and that is why there is no move button in
 * `ViewerChrome`.
 */
export function MovePicker({
  noun,
  startPrefix,
  forbiddenPrefix,
  currentPrefix,
  onMove,
  onClose,
}: Props) {
  const [prefix, setPrefix] = useState(startPrefix);
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
    getTree(prefix, "name")
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
  }, [prefix]);

  const inForbidden = forbiddenPrefix !== undefined && prefix.startsWith(forbiddenPrefix);
  const isCurrent = prefix === currentPrefix;
  const canMoveHere = !loading && !inForbidden && !isCurrent;

  const submit = useCallback(() => {
    setBusy(true);
    setError(null);
    onMove(prefix)
      .then(() => onClose())
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, [onClose, onMove, prefix]);

  return (
    <Dialog.Root open onOpenChange={(next: boolean) => !next && onClose()}>
      <Dialog.Backdrop />
      <Dialog.Popup className="flex max-h-[80vh] w-full max-w-lg flex-col gap-3 p-4">
        <Dialog.Title>Move {noun}</Dialog.Title>

        <Breadcrumbs.Root>
          {crumbs.map((crumb, index, all) => (
            <Breadcrumbs.Item
              key={crumb.prefix}
              current={index === all.length - 1}
              href="#"
              onClick={(event: React.MouseEvent) => {
                event.preventDefault();
                setPrefix(crumb.prefix);
              }}
            >
              {crumb.name}
            </Breadcrumbs.Item>
          ))}
        </Breadcrumbs.Root>

        <div className="min-h-40 flex-1 overflow-auto rounded-md border border-line">
          {loading && (
            <div className="flex h-40 items-center justify-center">
              <Spinner size="md" label="Loading folders" />
            </div>
          )}

          {!loading && (
            <div className="flex flex-col">
              {prefix !== ROOT_PREFIX && (
                <PickerRow up onSelect={() => setPrefix(parentPrefix(prefix))}>
                  Up one folder
                </PickerRow>
              )}

              {folders.map((folder) => (
                <PickerRow
                  key={folder.prefix}
                  // The folder being moved cannot be its own destination, and
                  // showing it greyed says why better than hiding it does.
                  disabled={folder.prefix === forbiddenPrefix}
                  onSelect={() => setPrefix(folder.prefix)}
                >
                  {folder.name}
                </PickerRow>
              ))}

              {folders.length === 0 && (
                <Text variant="caption" tone="muted" className="p-3">
                  No folders here — moving into this one is still fine.
                </Text>
              )}
            </div>
          )}
        </div>

        <Text variant="caption" tone="muted" className="truncate">
          Destination: {prefix || "/"}
        </Text>

        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>That did not work</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        <div className="flex items-center justify-end gap-2">
          <Button intent="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          {/* Disabled rather than absent, with the reason beside it: a button
              that vanishes when you navigate somewhere it cannot be used reads
              as a bug, not as an explanation. */}
          <Button size="sm" disabled={!canMoveHere || busy} onClick={submit}>
            {busy ? "Moving…" : isCurrent ? "Already here" : inForbidden ? "Not in itself" : "Move here"}
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
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]"
      >
        {up ? (
          <path d="M12 19V5m0 0-6 6m6-6 6 6" strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
        )}
      </svg>
      <Text variant="body" className="truncate">
        {children}
      </Text>
    </button>
  );
}
