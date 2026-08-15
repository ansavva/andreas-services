import { Text } from "@ansavva/design-system";

import { describeFolder } from "../../utils/format";

interface Props {
  name: string;
  onOpen: () => void;
}

export function FolderCard({ name, onOpen }: Props) {
  const { title, subtitle } = describeFolder(name);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-md border border-line bg-card px-3 py-2.5
                 text-left transition-colors hover:bg-surface-alt
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
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
  );
}
