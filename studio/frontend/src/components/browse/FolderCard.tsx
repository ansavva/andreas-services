import { useCallback, useState } from "react";

import { describeFolder } from "../../utils/format";
import { EntityRow } from "../entity/EntityRow";
import { ItemActions } from "../common/ItemActions";
import { RenameForm } from "../common/RenameForm";
import { FolderIcon } from "../common/icons";

interface Props {
  name: string;
  /**
   * The folder's full slash-joined *name* path.
   *
   * It used to be described as the S3 prefix, and both halves of that were
   * wrong: it is not a key, and no blob key beneath it starts with it. **It is
   * also no longer an address anything writes with** — every write takes node
   * ids — so the one job left to it is the one a path was always better at:
   * it is what a person types at the CLI, and it is what "Copy prefix" puts on
   * the clipboard.
   */
  prefix: string;
  onOpen: () => void;
  onRename: (name: string) => Promise<unknown>;
  /** Asks the page to open its destination picker on this folder. */
  onMove: () => void;
  onDelete: () => Promise<unknown>;
}

/**
 * A folder, drawn as a row.
 *
 * **It used to be a grid card, on its own ladder from everything below it** —
 * a folder full of folders and files read as two different kinds of listing
 * stacked on the page. It is `EntityRow` now: no thumbnail (a folder icon
 * stands in), no `to` (a Files tab is often driven by component state rather
 * than a URL — see `BrowserNav` — so opening one is always `onOpen`), and the
 * ⋯ menu rides in the `trailing` slot the same way a file's does.
 */
export function FolderCard({ name, prefix, onOpen, onRename, onMove, onDelete }: Props) {
  const { title, subtitle } = describeFolder(name);
  const [renaming, setRenaming] = useState(false);
  const stopRenaming = useCallback(() => setRenaming(false), []);

  return (
    <EntityRow
      title={title}
      subtitle={subtitle}
      thumb={{ icon: <FolderIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" /> }}
      onOpen={onOpen}
      trailing={
        // A folder has no object of its own, so what goes on the clipboard is
        // its name path. This used to claim that was what you want for an
        // `aws s3 ls`; it is not one, and the thing it is pasted into is the
        // `studio` CLI, which takes name paths and holds no AWS credentials.
        <ItemActions
          name={name}
          copyValue={prefix}
          copyNoun="prefix"
          onRename={() => setRenaming(true)}
          onMove={onMove}
          onDelete={onDelete}
        />
      }
    >
      {/* Renaming edits the folder's real name, not the prettified `title` a run
          folder is displayed under — `describeFolder` splits
          `2026-08-14_16-32-11_kling-yqp1jqf5` into a date and a slug for reading,
          and offering the slug alone as the thing to edit would drop the
          timestamp the whole library sorts on. */}
      {renaming && (
        <RenameForm
          name={name}
          onRename={onRename}
          onClose={stopRenaming}
          className="basis-full px-3 pb-3"
        />
      )}
    </EntityRow>
  );
}
