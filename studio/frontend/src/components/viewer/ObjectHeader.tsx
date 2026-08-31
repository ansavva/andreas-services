import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

import { PageBar, type Crumb } from "../layout/PageBar";
import type { FileEntry } from "../../types";
import { formatBytes, formatDate } from "../../utils/format";
import { ObjectActions } from "./ObjectActions";

interface HeaderProps {
  file: FileEntry;
  /** "2 of 3" — where this file sits in the feed. Absent while the count is unknown. */
  position?: string;
  /** Where the page sits. The context the address carries, as one crumb. */
  crumbs?: Crumb[];
  /** Passed to the actions — see `ObjectActions`' own `container`. */
  container?: HTMLElement | null;
  onRename?: (name: string) => Promise<unknown>;
  onDelete?: () => Promise<unknown>;
  describing?: boolean;
  onToggleDescribing?: () => void;
  onClose?: () => void;
}

/**
 * The open file's page header: where it sits, what it is, what can be done to it.
 *
 * **`ViewerChrome` was this, floating.** It was a gradient strip pinned over
 * the media with the name truncated into it, because the viewer was a
 * `fixed inset-x-0 z-50` takeover and there was no page to put a header on. The
 * object screen is an ordinary page inside `AppLayout`, so this is an ordinary
 * `PageBar` — the same one every other screen in the app uses, which is the
 * point: a file stopped being a mode and became a thing with an address.
 *
 * The facts are mono. A byte count, a date and a position are figures read
 * against each other as you step along a feed, and a proportional face makes
 * the line reflow under every one of those steps.
 */
export function ObjectHeader({
  file,
  position,
  crumbs,
  container,
  onRename,
  onDelete,
  describing = false,
  onToggleDescribing,
  onClose,
}: HeaderProps) {
  return (
    <PageBar
      crumbs={crumbs}
      actions={
        <ObjectActions
          file={file}
          container={container ?? null}
          onRename={onRename}
          onDelete={onDelete}
          describing={describing}
          onToggleDescribing={onToggleDescribing}
          onClose={onClose}
        />
      }
    >
      <Text variant="title" weight="medium" className="min-w-0 truncate">
        {file.name}
      </Text>
      <Text variant="caption" family="mono" tone="muted">
        {formatBytes(file.size)}
        {file.last_modified ? ` · ${formatDate(file.last_modified)}` : ""}
        {position ? ` · ${position}` : ""}
      </Text>
    </PageBar>
  );
}

interface DetailsProps {
  file: FileEntry;
  /**
   * A line under the facts — where this file sits, when nothing else says.
   *
   * Only the contextless screen supplies one. See `OwnerLink`.
   */
  aside?: ReactNode;
}

/**
 * What the file *shows*, beside the player rather than over it.
 *
 * The chrome used to truncate the description to one line because it was a
 * header laid on a photograph and there was nowhere for prose to go. A column
 * beside the media is that somewhere, so the whole caption is on screen and the
 * tags are readable without opening anything.
 *
 * It is read-only. Editing is `DescribePanel`, which takes this column's place
 * while it is open — one thing in one slot rather than a panel sliding over a
 * copy of itself.
 */
export function ObjectDetails({ file, aside }: DetailsProps) {
  const tags = file.tags ?? [];

  return (
    <section
      aria-label="File details"
      className="flex flex-col gap-3 border-t border-line pt-3 lg:border-t-0 lg:pt-0"
    >
      {file.description ? (
        <Text variant="body">{file.description}</Text>
      ) : (
        <Text variant="caption" tone="muted">
          No description yet.
        </Text>
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <Text
              key={tag}
              variant="caption"
              family="mono"
              className="rounded-xs bg-neutral-a3 px-1.5 py-0.5"
            >
              {tag}
            </Text>
          ))}
        </div>
      )}

      <Text variant="caption" family="mono" tone="muted" className="break-all">
        {file.key}
      </Text>

      {aside}
    </section>
  );
}
