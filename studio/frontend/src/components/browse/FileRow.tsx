import { useCallback, useState } from "react";

import { Badge, Text } from "@ansavva/design-system";

import { formatBytes, formatDate } from "../../utils/format";
import type { FileEntry } from "../../types";
import { ItemActions } from "../common/ItemActions";
import { RenameForm } from "../common/RenameForm";

interface Props {
  file: FileEntry;
  onOpen: () => void;
  onRename: (name: string) => Promise<unknown>;
  /** Asks the page to open its destination picker on this file, to move it. */
  onMove: () => void;
  /** The same picker, to copy it instead. */
  onCopyTo: () => void;
  onDelete: () => Promise<unknown>;
}

/** A non-media file — the run metadata JSON, a caption, a subject's profile. */
export function FileRow({ file, onOpen, onRename, onMove, onCopyTo, onDelete }: Props) {
  const viewable = file.kind === "text";
  const [renaming, setRenaming] = useState(false);
  const stopRenaming = useCallback(() => setRenaming(false), []);

  return (
    // The row's frame lives on this wrapper so the controls can sit *beside* the
    // opening button rather than inside it — every card, row and tile in this app
    // is itself a `<button>`, and a button inside a button is invalid HTML
    // browsers resolve by dropping one of them, unpredictably. A `.mp4`'s sibling
    // `result.json` is not viewable, but its key is still worth copying and it is
    // still worth deleting, so the hover highlight follows what is openable and
    // the controls do not.
    //
    // `flex-wrap` gives the rename field below a full line of its own rather than
    // the sliver left over beside the name.
    <div
      className={`flex w-full flex-wrap items-center gap-2 rounded-md border border-line bg-card pr-2
                  transition-colors ${viewable ? "hover:bg-surface-alt" : ""}`}
    >
      <button
        type="button"
        onClick={onOpen}
        disabled={!viewable}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-md px-3 py-2.5 text-left
                   disabled:cursor-default disabled:opacity-60
                   focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]"
        >
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
          <path d="M14 3v5h5" />
        </svg>

        <span className="min-w-0 flex-1">
          <Text variant="body" className="truncate">
            {file.name}
          </Text>
          <Text variant="caption" tone="muted" className="truncate">
            {formatBytes(file.size)} · {formatDate(file.last_modified)}
          </Text>
        </span>
      </button>

      {file.language && <Badge intent="neutral">{file.language}</Badge>}

      <ItemActions
        name={file.name}
        copyValue={file.key}
        onRename={() => setRenaming(true)}
        onMove={onMove}
        onCopyTo={onCopyTo}
        onDelete={onDelete}
      />

      {renaming && (
        <RenameForm
          name={file.name}
          onRename={onRename}
          onClose={stopRenaming}
          className="basis-full px-3 pb-3"
        />
      )}
    </div>
  );
}
