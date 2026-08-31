import { Badge, Text } from "@ansavva/design-system";

import { formatDate } from "../../utils/format";
import type { RunKind, RunStatus, RunSummary } from "../../types";
import { MediaThumb } from "../media/MediaThumb";
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
 * **Chrome is the caller's.** Filters, paging, empty states and headings differ
 * by screen and belong to the screen; what a RUN looks like does not.
 */
export const STATUS_INTENT: Record<RunStatus, "neutral" | "success" | "danger" | "warning"> = {
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
  onOpen,
  empty,
}: {
  runs: RunRow[];
  onOpen: (run: RunRow) => void;
  /** Shown instead of the rows when there are none. */
  empty?: React.ReactNode;
}) {
  if (runs.length === 0) return <>{empty ?? null}</>;

  return (
    <div className="flex flex-col gap-2">
      {runs.map((run) => (
        <button
          key={run.id}
          type="button"
          onClick={() => onOpen(run)}
          className="flex w-full items-center gap-3 rounded-none border border-line bg-card p-2 text-left
                     transition-colors hover:bg-surface-alt
                     focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {/* The thumbnail is the run's first output, signed by the listing —
              what the projection on the listing row is for. A run that has not
              produced anything yet shows its kind instead; a caller that reads
              no thumbnails at all draws neither, rather than a row of empty
              squares. */}
          {(run.thumb || run.kind) && (
            <span className="size-14 shrink-0 overflow-hidden rounded-none border border-line bg-surface-alt">
              {run.thumb ? (
                <MediaThumb nodeId={run.thumb.node} url={run.thumb.url} name="" aspect="auto" />
              ) : (
                <span className="flex h-full w-full items-center justify-center text-xs text-muted">
                  {run.kind as RunKind}
                </span>
              )}
            </span>
          )}

          <span className="min-w-0 flex-1">
            {/* A run has no label. The date is what identifies one to a person,
                which is what the old slug was imitating by carrying a timestamp;
                the model is the next most useful thing about it. */}
            {/* A date standing in for a name, and a model id — both are
                values rather than prose, so both are mono. */}
            <Text variant="body" family="mono" className="truncate">
              {run.created ? formatDate(run.created) : run.id}
            </Text>
            {run.model && (
              <Text variant="caption" tone="muted" className="block truncate font-mono">
                {run.model}
              </Text>
            )}
          </span>

          {run.role && (
            <Badge intent="neutral" className="font-mono">
              {run.role}
            </Badge>
          )}
          {run.status && (
            <Badge intent={STATUS_INTENT[run.status]} className="font-mono">
              {run.status}
            </Badge>
          )}

          {/* Recorded when the provider reports it and never computed —
              Replicate's prediction metrics differ by model, and a number this
              app worked out itself would be a guess wearing a currency sign. */}
          {run.cost !== undefined && (
            <Text variant="caption" tone="muted" className="w-20 shrink-0 text-right font-mono tabular-nums">
              {formatCost(run.cost, "—")}
            </Text>
          )}
        </button>
      ))}
    </div>
  );
}
