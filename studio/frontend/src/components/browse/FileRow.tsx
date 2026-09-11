import { useCallback, useState } from "react";

import { Checkbox } from "@ansavva/design-system";

import { formatBytes, formatDate } from "../../utils/format";
import type { FileEntry } from "../../types";
import { EntityRow } from "../entity/EntityRow";
import { ItemActions } from "../common/ItemActions";
import { RenameForm } from "../common/RenameForm";
import { CheckIcon, FileIcon } from "../common/icons";

interface Props {
  file: FileEntry;
  /**
   * Selection, mirroring the media grid's.
   *
   * A folder's images could be selected and acted on in bulk and its files
   * could not, so deleting five `result.json` files was five trips through a
   * per-row menu. The checkbox is a sibling of the opening link for the same
   * reason the tile's is: `EntityRow`'s `leading` slot exists because a
   * checkbox cannot sit inside an `<a>`.
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
    <EntityRow
      title={file.name}
      subtitle={`${formatBytes(file.size)} · ${formatDate(file.last_modified)}`}
      status={file.language}
      thumb={{ icon: <FileIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" /> }}
      selected={selected}
      selecting={selectionActive}
      // A link only while there is somewhere to go and selection is not
      // claiming the click — the same condition the old `<a>` branch tested.
      to={viewable && !selectionActive ? to : undefined}
      // Selection mode wins over opening: a press extends the selection
      // instead, reading `shiftKey` itself the way the checkbox's own handler
      // does. Outside selection mode an unviewable row opens nothing.
      onOpen={
        selectionActive
          ? (event) => onToggleSelect(event.shiftKey)
          : viewable
            ? onOpen
            : undefined
      }
      leading={
        // Hidden until wanted, like the tile's — a folder of rows is not a
        // column of checkboxes over the names it exists to show — but always
        // visible once anything is picked, and wherever there is no pointer to
        // hover with.
        <Checkbox.Root
          checked={selected}
          onClick={(event) => {
            event.preventDefault();
            onToggleSelect(event.shiftKey);
          }}
          aria-label={`Select ${file.name}`}
          className={`ms-2 shrink-0 transition-opacity focus-visible:opacity-100
                      group-hover:opacity-100 pointer-coarse:opacity-100
                      ${selectionActive ? "opacity-100" : "opacity-0"}`}
        >
          <Checkbox.Indicator>
            <CheckIcon className="size-3.5 fill-none stroke-current stroke-[3]" />
          </Checkbox.Indicator>
        </Checkbox.Root>
      }
      trailing={
        <ItemActions
          name={file.name}
          copyValue={file.key}
          onRename={() => setRenaming(true)}
          onMove={onMove}
          onCopyTo={onCopyTo}
          onDelete={onDelete}
        />
      }
    >
      {renaming && (
        <RenameForm
          name={file.name}
          onRename={onRename}
          onClose={stopRenaming}
          className="basis-full px-3 pb-3"
        />
      )}
    </EntityRow>
  );
}
