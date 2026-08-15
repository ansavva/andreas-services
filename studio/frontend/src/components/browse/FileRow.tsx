import { Badge, Text } from "@ansavva/design-system";

import { formatBytes, formatDate } from "../../utils/format";
import type { FileEntry } from "../../types";
import { CopyKeyButton } from "../common/CopyKeyButton";

interface Props {
  file: FileEntry;
  onOpen: () => void;
}

/** A non-media file — the run metadata JSON, a caption, a subject's profile. */
export function FileRow({ file, onOpen }: Props) {
  const viewable = file.kind === "text";

  return (
    // The row's frame moved out to this wrapper so the copy button can sit
    // beside the opening button rather than inside it. A `.mp4`'s sibling
    // `result.json` is not viewable, but its key is still worth copying — so
    // the hover highlight follows what is openable, and the copy button does
    // not.
    <div
      className={`flex w-full items-center gap-2 rounded-md border border-line bg-card pr-2
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

      <CopyKeyButton value={file.key} />
    </div>
  );
}
