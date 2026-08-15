import { Badge, Text } from "@ansavva/design-system";

import { formatBytes, formatDate } from "../../utils/format";
import type { FileEntry } from "../../types";

interface Props {
  file: FileEntry;
  onOpen: () => void;
}

/** A non-media file — the run metadata JSON, a caption, a subject's profile. */
export function FileRow({ file, onOpen }: Props) {
  const viewable = file.kind === "text";

  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={!viewable}
      className="flex w-full items-center gap-3 rounded-md border border-line bg-card px-3 py-2.5
                 text-left transition-colors hover:bg-surface-alt disabled:cursor-default
                 disabled:opacity-60 disabled:hover:bg-card
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
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

      {file.language && <Badge intent="neutral">{file.language}</Badge>}
    </button>
  );
}
