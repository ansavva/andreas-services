import { Text } from "@ansavva/design-system";

import { describeFolder } from "../../utils/format";
import { CopyKeyButton } from "../common/CopyKeyButton";

interface Props {
  name: string;
  /** The folder's full S3 prefix — what a key under it starts with. */
  prefix: string;
  onOpen: () => void;
}

export function FolderCard({ name, prefix, onOpen }: Props) {
  const { title, subtitle } = describeFolder(name);

  return (
    // Frame on the wrapper, opening button and copy button inside it — a
    // button cannot contain another button. See `CopyKeyButton`.
    <div
      className="flex w-full items-center gap-2 rounded-md border border-line bg-card pr-2
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

      {/* A folder has no object of its own, so what goes on the clipboard is
          the prefix — which is what you actually want for an `aws s3 ls`. */}
      <CopyKeyButton value={prefix} noun="prefix" />
    </div>
  );
}
