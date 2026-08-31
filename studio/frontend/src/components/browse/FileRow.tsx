import { useCallback, useState } from "react";

import { Badge, Text } from "@ansavva/design-system";

import { formatBytes, formatDate } from "../../utils/format";
import type { FileEntry } from "../../types";
import { ItemActions } from "../common/ItemActions";
import { RenameForm } from "../common/RenameForm";
import { CheckIcon, FileIcon } from "../common/icons";
import { Checkbox } from "@ansavva/design-system";

/** One shape for the row whether it ends up a link or a button. */
const ROW =
  "flex min-w-0 flex-1 items-center gap-3 rounded-none px-3 py-2.5 text-left " +
  "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary";

interface Props {
  file: FileEntry;
  /**
   * Selection, mirroring the media grid's.
   *
   * A folder's images could be selected and acted on in bulk and its files
   * could not, so deleting five `result.json` files was five trips through a
   * per-row menu. The checkbox is a sibling of the opening button for the same
   * reason the tile's is: both are `<button>` elements and one cannot contain
   * the other.
   */
  selected: boolean;
  /** True once anything in the folder is picked — a press then extends rather than opens. */
  selectionActive: boolean;
  onToggleSelect: (extend: boolean) => void;
  onOpen: () => void;
  /**
   * Where opening it goes, as an address — see `MediaTile.to`.
   *
   * A row is not always openable (`viewable` is false for anything the viewer
   * cannot draw), so this is a link only when there is somewhere to go.
   */
  to?: string;
  onRename: (name: string) => Promise<unknown>;
  /** Asks the page to open its destination picker on this file, to move it. */
  onMove: () => void;
  /** The same picker, to copy it instead. */
  onCopyTo: () => void;
  onDelete: () => Promise<unknown>;
}

/** A non-media file — the run metadata JSON, a caption, a subject's profile. */
export function FileRow({
  file,
  selected,
  selectionActive,
  onToggleSelect,
  onOpen,
  to,
  onRename,
  onMove,
  onCopyTo,
  onDelete,
}: Props) {
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
      className={`group flex w-full flex-wrap items-center gap-2 rounded-none border bg-card pr-2
                  transition-colors ${viewable && !selectionActive ? "hover:bg-surface-alt" : ""}
                  ${selected ? "border-primary ring-1 ring-primary" : "border-line"}`}
    >
      {/* Hidden until wanted, like the tile's — a folder of rows is not a column
          of checkboxes over the names it exists to show — but always visible
          once anything is picked, and wherever there is no pointer to hover
          with. */}
      <Checkbox.Root
        checked={selected}
        onClick={(event) => {
          event.preventDefault();
          onToggleSelect(event.shiftKey);
        }}
        aria-label={`Select ${file.name}`}
        className={`ms-3 shrink-0 transition-opacity focus-visible:opacity-100
                    group-hover:opacity-100 pointer-coarse:opacity-100
                    ${selectionActive ? "opacity-100" : "opacity-0"}`}
      >
        <Checkbox.Indicator>
          <CheckIcon className="size-3.5 fill-none stroke-current stroke-[3]" />
        </Checkbox.Indicator>
      </Checkbox.Root>

      {/* An `<a>` when there is an address and the row can be opened, so
          command-click, middle-click and "copy link" all work — a `<button>`
          offers none of them. Selection mode and an unviewable row both fall
          back to the button, because neither has a destination. */}
      {to && viewable && !selectionActive ? (
        <a
          href={to}
          onClick={(event) => {
            if (
              event.metaKey ||
              event.ctrlKey ||
              event.shiftKey ||
              event.altKey
            )
              return;
            event.preventDefault();
            onOpen();
          }}
          className={ROW}
        >
          <FileIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" />
          <span className="min-w-0 flex-1">
            <Text variant="body" className="truncate">
              {file.name}
            </Text>
            <Text
              variant="caption"
              tone="muted"
              className="truncate font-mono tabular-nums"
            >
              {formatBytes(file.size)} · {formatDate(file.last_modified)}
            </Text>
          </span>
        </a>
      ) : (
        <button
          type="button"
          // Once anything is picked the folder is in selection mode and a press
          // extends rather than opens — the same bargain the media grid makes.
          onClick={(event) =>
            selectionActive ? onToggleSelect(event.shiftKey) : onOpen()
          }
          disabled={!viewable && !selectionActive}
          className={`${ROW} disabled:cursor-default disabled:opacity-60`}
        >
          <FileIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" />

          <span className="min-w-0 flex-1">
            <Text variant="body" className="truncate">
              {file.name}
            </Text>
            {/* A byte count and a timestamp — the canonical metadata pair, and
              the reason a mono role exists. */}
            <Text
              variant="caption"
              tone="muted"
              className="truncate font-mono tabular-nums"
            >
              {formatBytes(file.size)} · {formatDate(file.last_modified)}
            </Text>
          </span>
        </button>
      )}

      {file.language && (
        <Badge intent="neutral" className="font-mono">
          {file.language}
        </Badge>
      )}

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
