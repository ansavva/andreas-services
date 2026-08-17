import { useCallback, useState } from "react";

import { Text } from "@ansavva/design-system";

import { describeFolder } from "../../utils/format";
import { ItemActions } from "../common/ItemActions";
import { RenameForm } from "../common/RenameForm";

interface Props {
  name: string;
  /** The folder's full S3 prefix — what a key under it starts with. */
  prefix: string;
  onOpen: () => void;
  onRename: (name: string) => Promise<unknown>;
  /** Asks the page to open its destination picker on this folder. */
  onMove: () => void;
  onDelete: () => Promise<unknown>;
}

export function FolderCard({ name, prefix, onOpen, onRename, onMove, onDelete }: Props) {
  const { title, subtitle } = describeFolder(name);
  const [renaming, setRenaming] = useState(false);
  const stopRenaming = useCallback(() => setRenaming(false), []);

  return (
    // Frame on the wrapper, opening button and controls inside it — a button
    // cannot contain another button. See `CopyKeyButton`.
    //
    // `flex-wrap` is load-bearing rather than defensive: the rename field below
    // is `basis-full`, so it takes a line of its own instead of being squeezed
    // into what is left of this one beside the name.
    <div
      className="flex w-full flex-wrap items-center gap-2 rounded-md border border-line bg-card pr-2
                 transition-colors hover:bg-surface-alt"
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-md px-3 py-2.5 text-left
                   focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]"
        >
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
        </svg>

        <span className="min-w-0 flex-1">
          <Text variant="body" weight="medium" className="truncate">
            {title}
          </Text>
          {subtitle && (
            <Text variant="caption" tone="muted" className="truncate tabular-nums">
              {subtitle}
            </Text>
          )}
        </span>
      </button>

      {/* A folder has no object of its own, so what goes on the clipboard is the
          prefix — which is what you actually want for an `aws s3 ls`. */}
      <ItemActions
        name={name}
        copyValue={prefix}
        copyNoun="prefix"
        onRename={() => setRenaming(true)}
        onMove={onMove}
        onDelete={onDelete}
      />

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
    </div>
  );
}
