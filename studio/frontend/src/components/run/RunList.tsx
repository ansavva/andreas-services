import { Text } from "@ansavva/design-system";

import { formatDate } from "../../utils/format";
import type { RunStatus, RunSummary } from "../../types";
import { EntityRow, type RowBadge } from "../entity/EntityRow";
import { formatCost } from "../../utils/cost";

/**
 * The one way a run is drawn in a list, wherever a list of runs appears.
 *
 * **Three screens drew a run row and no two agreed.** A project's table had a
 * thumbnail, the date as the headline, the model under it, the status on a full
 * seven-value intent map and the cost right-aligned. A character's tab had no
 * thumbnail, the date as the headline, and a status badge that only knew
 * `failed` — so a `running` run read amber on one page and grey on the other,
 * for the same run. A storyboard had no row at all, only a link per tile.
 *
 * The rows were never *meant* to differ; they were written months apart and
 * each was reasonable on its own. That is what this component is for — not to
 * save lines, but so that a status colour means one thing across the app.
 *
 * The row itself is `EntityRow`'s: what a run adds is which fields go where.
 * **Chrome is the caller's.** Filters, paging, empty states and headings differ
 * by screen and belong to the screen; what a RUN looks like does not.
 */
export const STATUS_INTENT: Record<
  RunStatus,
  "neutral" | "success" | "danger" | "warning"
> = {
  // Unsubmitted. `approved` is a warning rather than a success on purpose: it
  // means money is about to be spent and has not been yet, which is a state
  // worth noticing rather than a job well done.
  draft: "neutral",
  approved: "warning",
  discarded: "neutral",
  pending: "neutral",
  running: "warning",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
  // A synthetic run wrapping an artifact that already existed — see `RunStatus`.
  adopted: "neutral",
};

/**
 * What a row needs. A superset of nothing — every field is optional except the
 * id, because the three callers know different amounts.
 *
 * A project's listing carries a signed thumbnail and a cost; a scene's shot
 * carries neither, because expanding a thumbnail per run would be a second
 * batch read for a board that already draws the frames themselves. A row
 * renders what it is given and leaves out what it is not, rather than each
 * caller inventing a different shape for the same absence.
 */
export interface RunRow extends Partial<Omit<RunSummary, "id">> {
  id: string;
  /** What this run is TO the thing listing it — a scene shot's `clip`, `sample`,
      `handoff`, `earlier take`. Absent everywhere the list is already of one
      kind of thing. */
  role?: string;
}

export function RunList({
  runs,
  to,
  empty,
}: {
  runs: RunRow[];
  /** A run's address. The caller knows the project; a row may not. */
  to: (run: RunRow) => string;
  /** Shown instead of the rows when there are none. */
  empty?: React.ReactNode;
}) {
  if (runs.length === 0) return <>{empty ?? null}</>;

  return (
    <div className="flex flex-col">
      {runs.map((run) => {
        const status: RowBadge[] = [];
        if (run.role) status.push(run.role);
        if (run.status) status.push({ label: run.status, intent: STATUS_INTENT[run.status] });

        return (
          <EntityRow
            key={run.id}
            // A run has no label. The date is what identifies one to a person,
            // and the model is the next most useful thing about it — both
            // values rather than prose, so both mono.
            title={run.created ? formatDate(run.created) : run.id}
            mono
            subtitle={run.model}
            // The thumbnail is the run's first output, signed by the listing.
            // `isVideo` is not optional: a video run's first output is an
            // `.mp4`, and without it the row drew a broken image. A run that
            // has produced nothing shows its kind; a caller that reads no
            // thumbnails draws neither.
            thumb={
              run.thumb
                ? { node: run.thumb.node, url: run.thumb.url, isVideo: run.kind === "video" }
                : run.kind
                  ? { placeholder: run.kind }
                  : undefined
            }
            status={status}
            to={to(run)}
            // Recorded when the provider reports it and never computed —
            // Replicate's prediction metrics differ by model, and a number this
            // app worked out itself would be a guess wearing a currency sign.
            trailing={
              run.cost !== undefined && (
                <Text
                  variant="caption"
                  tone="muted"
                  className="w-20 shrink-0 text-right font-mono tabular-nums"
                >
                  {formatCost(run.cost)}
                </Text>
              )
            }
          />
        );
      })}
    </div>
  );
}
