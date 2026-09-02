import { useCallback, useEffect, useState } from "react";

import { Alert, Breadcrumbs, Button, Dialog, Text } from "@ansavva/design-system";

import { ApertureSpinner } from "../common/Aperture";
import { getFolder } from "../../apis/studio";
import type { Crumb, FileEntry, FolderEntry } from "../../types";
import type { FolderId } from "../../utils/location";
import { ArrowUpIcon, FolderIcon } from "../common/icons";
import { MediaThumb } from "../media/MediaThumb";
import { TagFilter } from "./TagFilter";

interface Props {
  /** Written into the title — "an image to send". */
  noun: string;
  /** Where the picker opens. Normally the folder nearest what is being added to. */
  startId: FolderId;
  /**
   * Nodes already chosen, drawn as taken rather than hidden.
   *
   * A run sending the same picture twice is a mistake with no error message —
   * the model is handed a duplicate and the positions after it shift — so the
   * tile says it is already in the list instead of quietly letting it in again.
   */
  taken?: ReadonlySet<string>;
  onSubmit: (files: FileEntry[]) => Promise<unknown>;
  onClose: () => void;
}

/**
 * Pick media by browsing to it — the file-shaped twin of `DestinationPicker`.
 *
 * Separate from that one rather than a mode of it, because they are looking for
 * different things: a destination is a folder and the files in it are noise,
 * while this is choosing pictures and the folders are only the way there. The
 * two do share the shape — crumbs, an up row, an id submitted and a path shown —
 * and that is deliberate, since a person moving a file and a person adding one to
 * a run are walking the same tree.
 *
 * **It hands back the listing rows it drew, and the caller sends the ids.** The
 * name and the signed URL come along because a picture added to a list has to be
 * drawable before the save round-trips — not because they mean anything to a
 * write. What a send actually IS, and where the API says the picture came from,
 * arrives on the response to the write and replaces all of this.
 *
 * Multi-select, because the thing being built is an ordered list: adding six
 * references one dialog at a time is six trips through the same folder.
 */
export function MediaPicker({ noun, startId, taken, onSubmit, onClose }: Props) {
  const [folderId, setFolderId] = useState<FolderId>(startId);
  const [folders, setFolders] = useState<FolderEntry[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  /**
   * Tags narrowing the listing — and, while any are on, widening its SCOPE.
   *
   * A picker is where the tags matter most: what used to be "open the character,
   * open `reference/`, open `face/`" is `default` + `face` from wherever you
   * happen to be standing, because a tag search reaches the whole branch.
   */
  const [tags, setTags] = useState<string[]>([]);
  // Extracted and stable: `tags` is a new array every render, so the listing
  // effect would re-run forever if it depended on the array itself.
  const asked = tags.join(",");
  const [facet, setFacet] = useState<Record<string, number>>({});
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /**
   * Chosen, IN THE ORDER THEY WERE CHOSEN, and across folders.
   *
   * An array rather than a set for the first reason and kept outside the
   * listing effect for the second: position is the payload — a prompt citing
   * "the first image" is citing this order — and a character's face references
   * and a project's plate rarely sit in one folder.
   */
  const [chosen, setChosen] = useState<FileEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    // By name, like the destination picker: "newest first" answers a question
    // nobody asks while looking for a particular picture.
    getFolder(folderId === null ? {} : { node: folderId }, "name", {
      tag: asked ? asked.split(",") : [],
    })
      .then((result) => {
        if (cancelled) return;
        // **Folders are dropped while a tag search is on.** They are the way to
        // the pictures at one level; in a result set gathered from the whole
        // branch they are not on the way to anything.
        setFolders(result.depth === "all" ? [] : result.folders);
        setFiles(result.files.filter((file) => file.kind === "image" || file.kind === "video"));
        setCrumbs(result.breadcrumbs);
        setFacet(result.tags ?? {});
        setSearching(result.depth === "all");
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
  }, [folderId, asked]);

  const parent = crumbs.at(-2)?.id;
  const shownPath = crumbs.at(-1)?.prefix ?? "";

  const toggle = useCallback((file: FileEntry) => {
    setChosen((current) =>
      current.some((each) => each.id === file.id)
        ? current.filter((each) => each.id !== file.id)
        : [...current, file],
    );
  }, []);

  const submit = useCallback(() => {
    if (chosen.length === 0) return;
    setBusy(true);
    setError(null);
    onSubmit(chosen)
      .then(() => onClose())
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }, [chosen, onClose, onSubmit]);

  return (
    <Dialog.Root open onOpenChange={(next: boolean) => !next && onClose()}>
      <Dialog.Backdrop />
      <Dialog.Popup className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 p-4">
        <Dialog.Title>Add {noun}</Dialog.Title>

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

        <TagFilter value={tags} onChange={setTags} facet={facet} searching={searching} />

        <div className="min-h-48 flex-1 overflow-auto rounded-none border border-line">
          {loading && (
            <div className="flex h-48 items-center justify-center">
              <ApertureSpinner size="md" label="Loading folder" />
            </div>
          )}

          {!loading && (
            <div className="flex flex-col">
              {parent !== undefined && (
                <button
                  type="button"
                  onClick={() => setFolderId(parent)}
                  className="flex items-center gap-2 border-b border-line px-3 py-2.5 text-left
                             transition-colors hover:bg-surface-alt
                             focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
                >
                  <ArrowUpIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" />
                  <Text variant="body">Up one folder</Text>
                </button>
              )}

              {folders.map((folder) => (
                <button
                  key={folder.id}
                  type="button"
                  onClick={() => setFolderId(folder.id)}
                  className="flex items-center gap-2 border-b border-line px-3 py-2.5 text-left
                             transition-colors hover:bg-surface-alt
                             focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
                >
                  <FolderIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" />
                  <Text variant="body" className="truncate">
                    {folder.name}
                  </Text>
                </button>
              ))}

              {files.length > 0 && (
                // The same density as every other media grid in the app: two
                // columns on a phone rather than one column of enormous tiles.
                <div className="grid grid-cols-2 gap-2 p-2 sm:grid-cols-4 md:grid-cols-5">
                  {files.map((file) => (
                    <Tile
                      key={file.id}
                      file={file}
                      position={chosen.findIndex((each) => each.id === file.id)}
                      already={taken?.has(file.id) ?? false}
                      onToggle={() => toggle(file)}
                    />
                  ))}
                </div>
              )}

              {/* Two sentences, because a search that found nothing and a
                  folder that holds nothing are different facts. "Nothing here"
                  is wrong when the search covered the whole branch — it names
                  the folder you are standing in, which is not where it looked. */}
              {files.length === 0 && folders.length === 0 && !searching && (
                <Text variant="caption" tone="muted" className="p-3">
                  Nothing here.
                </Text>
              )}

              {files.length === 0 && folders.length === 0 && searching && (
                <Text variant="caption" tone="muted" className="p-3">
                  Nothing under this folder is tagged {tags.join(" + ")}.
                </Text>
              )}
            </div>
          )}
        </div>

        <Text variant="caption" tone="muted" className="truncate">
          In: {shownPath || "/"}
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
          <Button size="sm" disabled={chosen.length === 0 || busy} onClick={submit}>
            {busy
              ? "Adding…"
              : chosen.length === 0
                ? "Nothing chosen"
                : `Add ${chosen.length}`}
          </Button>
        </div>
      </Dialog.Popup>
    </Dialog.Root>
  );
}

/**
 * One file, as a thumbnail that can be picked.
 *
 * **The number, not a tick.** What is being built is an ordered list, so the
 * badge says *where* in it this picture landed — which is the only part of a
 * selection that a checkmark cannot show and that the payload depends on.
 */
function Tile({
  file,
  position,
  already,
  onToggle,
}: {
  file: FileEntry;
  /** 0-based index in the selection, or `-1` when it is not in it. */
  position: number;
  already: boolean;
  onToggle: () => void;
}) {
  const chosen = position >= 0;

  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={already}
      aria-pressed={chosen}
      aria-label={already ? `${file.name} — already sent` : file.name}
      title={file.name}
      className={`relative flex flex-col gap-1 rounded-none border p-1 text-left transition-colors
                  disabled:cursor-default disabled:opacity-40
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                  ${chosen ? "border-primary bg-surface-alt" : "border-line hover:bg-surface-alt"}`}
    >
      <MediaThumb
        nodeId={file.id}
        url={file.url}
        name={file.name}
        isVideo={file.kind === "video"}
        aspect="portrait"
        dimmed={chosen}
        className="w-full rounded-none"
      />
      <Text variant="caption" tone="muted" className="truncate">
        {already ? "already sent" : file.name}
      </Text>
      {chosen && (
        <span
          className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-full
                     bg-primary font-body text-xs text-primary-text"
        >
          {position + 1}
        </span>
      )}
    </button>
  );
}
