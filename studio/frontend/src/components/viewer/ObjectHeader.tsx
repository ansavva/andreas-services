import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

import { useArmed } from "../../hooks/useArmed";
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
  onDelete?: () => Promise<unknown>;
  editing?: boolean;
  onToggleEditing?: () => void;
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
 * **Copy, Edit and Download stay reachable icons; Delete moved behind `⋯`.**
 * Every other page keeps its destructive control off the row of things
 * pressed on every visit, and this one used to be the exception — five icons
 * in a line, one of them red. It arms in place inside the menu now, the same
 * machine `ItemActions`' delete item runs on: unarmed, the press is swallowed
 * and the label turns red and restates what it destroys; armed, it is let
 * through and the menu closes as any selection does.
 *
 * The facts are mono. A byte count, a date and a position are figures read
 * against each other as you step along a feed, and a proportional face makes
 * the line reflow under every one of those steps.
 */
export function ObjectHeader({
  file,
  position,
  crumbs,
  onDelete,
  editing = false,
  onToggleEditing,
  onClose,
}: HeaderProps) {
  const destroy = useArmed({ onFire: async () => onDelete?.() });

  return (
    <PageBar
      crumbs={crumbs}
      title={file.name}
      meta={
        <Text variant="caption" family="mono" tone="muted">
          {formatBytes(file.size)}
          {file.last_modified ? ` · ${formatDate(file.last_modified)}` : ""}
          {position ? ` · ${position}` : ""}
        </Text>
      }
      actions={
        <ObjectActions
          file={file}
          editing={editing}
          onToggleEditing={onToggleEditing}
          onClose={onClose}
        />
      }
      menu={
        onDelete
          ? [
              {
                label: destroy.busy
                  ? "Deleting…"
                  : destroy.armed
                    ? "Confirm — delete this file"
                    : "Delete",
                danger: destroy.armed || destroy.busy,
                disabled: destroy.busy,
                onClick: (event) => {
                  if (!destroy.armed) event.preventDefault();
                  destroy.press();
                },
                itemProps: destroy.handlers,
              },
            ]
          : undefined
      }
      onMenuOpenChange={(open) => {
        if (!open) destroy.disarm();
      }}
    />
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
 * It is read-only, and it stays on screen. Editing is `FileDetailsPanel`, in a
 * drawer over the page — it used to take this column's place instead, which
 * meant opening the editor removed the thing being edited from view.
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
