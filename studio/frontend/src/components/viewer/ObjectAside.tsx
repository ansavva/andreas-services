import { Fragment, type ReactNode } from "react";

import { Badge, Text } from "@ansavva/design-system";

import { EmptyState } from "../common/EmptyState";
import type { FileEntry } from "../../types";
import { formatBytes, formatDate } from "../../utils/format";
import { ObjectActions } from "./ObjectActions";

/**
 * The column beside the player: everything the open file says about itself,
 * and everything that can be done to it.
 *
 * **`ObjectHeader` was this, spread across the top of the page.** The file's
 * name and facts were a `PageBar` title and the controls were that bar's
 * `actions`, which put them a full page-width away from the description, tags
 * and key describing the same file — and, on a phone, put a five-icon row
 * between the crumb and everything it was about. All of it is one column now.
 * What is left on the bar is the one thing that is about the PAGE rather than
 * the file: where it sits.
 */

interface ControlsProps {
  file: FileEntry;
  /** "2 of 3" — where this file sits in the feed. Absent while the count is unknown. */
  position?: string;
  onDelete?: () => Promise<unknown>;
  editing?: boolean;
  onToggleEditing?: () => void;
  onClose?: () => void;
  className?: string;
}

/**
 * The controls that act on the file, and where it sits in the feed.
 *
 * **The file's own facts are not here — they are the labelled list in
 * `ObjectDetails`.** They were a mono run-on line above this row: `164 KB ·
 * Aug 26, 2026, 10:19 PM · 71 of 71`, three unlabelled values separated by
 * interpuncts, with the name a heading above them and the path a second loose
 * line at the bottom of the column. Nothing said which figure was which, and
 * the four facts were in three different places. One labelled list says all
 * of it.
 *
 * The position stays behind, because it is the one figure in that line that
 * was never about the FILE — it is where you are in the feed, which changes
 * with the `?in=` and belongs beside the controls that walk it.
 */
export function ObjectControls({
  file,
  position,
  onDelete,
  editing = false,
  onToggleEditing,
  onClose,
  className,
}: ControlsProps) {
  return (
    <header className={`flex min-w-0 items-center gap-2 ${className ?? ""}`}>
      {/* `-ml-1.5` because an icon button's box is wider than its glyph: the
          row lines up with the column's text edge optically, not by its own. */}
      <div className="-ml-1.5 flex min-w-0 flex-wrap items-center gap-0.5">
        <ObjectActions
          file={file}
          onDelete={onDelete}
          editing={editing}
          onToggleEditing={onToggleEditing}
          onClose={onClose}
        />
      </div>

      {position && (
        // Mono, so the figures do not reflow under every step along the feed.
        <Text variant="caption" family="mono" tone="muted" className="ml-auto shrink-0">
          {position}
        </Text>
      )}
    </header>
  );
}

interface DetailsProps {
  file: FileEntry;
  /**
   * A line under the properties — where this file sits, when nothing else says.
   *
   * Only the contextless screen supplies one. See `OwnerLink`.
   */
  aside?: ReactNode;
}

/**
 * What the file shows and what it is, beside the player rather than over it.
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
        <EmptyState title="No description yet." />
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <Badge key={tag} intent="neutral" size="sm" className="font-mono">
              {tag}
            </Badge>
          ))}
        </div>
      )}

      <FileProperties file={file} />

      {aside}
    </section>
  );
}

/**
 * The file's own facts, labelled, one line each.
 *
 * **A `<dl>` and nothing else — no rules, no bands, no cell padding.** This was
 * a striped `Table` for one revision and read as a spreadsheet dropped into a
 * sidebar: five zebra rows of chrome around ten short words. The pairs are
 * what there is to see, so the only things drawn are the pairs — a quiet
 * label, the value beside it, and whitespace doing the aligning.
 *
 * Still a definition list rather than divs, because that is what a screen
 * reader needs to read "Path" with the value that follows it. The markup keeps
 * the semantics the table had; what went is the furniture.
 *
 * Values are mono and break anywhere. A path and a filename are strings you
 * compare character by character, and both are longer than 20rem.
 */
function FileProperties({ file }: { file: FileEntry }) {
  const rows: Array<[string, string]> = [
    ["Name", file.name],
    ["Type", file.content_type ?? file.kind],
    ["Size", formatBytes(file.size)],
    ...(file.last_modified
      ? [["Modified", formatDate(file.last_modified)] as [string, string]]
      : []),
    ["Path", file.key],
  ];

  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5">
      {rows.map(([label, value]) => (
        <Fragment key={label}>
          <dt>
            <Text as="span" variant="caption" tone="muted">
              {label}
            </Text>
          </dt>
          <dd className="min-w-0">
            <Text as="span" variant="caption" family="mono" className="break-all">
              {value}
            </Text>
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}
