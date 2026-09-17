import type { InfiniteData, QueryClient, QueryFilters } from "@tanstack/react-query";

import type { RunFeedPage, RunFeedRow, RunRecord } from "../../types";
import { rowOfRecord } from "./rowOfRecord";

/**
 * Write records into the feed's cached pages, in place.
 *
 * `GET /api/runs/<id>` answers a run whole — plan, sends, outputs, all signed —
 * so a record in hand is a row the feed can draw without re-reading the page
 * the run sits on. Two callers: `useRunWatch`, which patches a run that has
 * LANDED, and a person pressing Refresh, which patches whatever came back.
 *
 * `when` is the caller's rule for rewriting a row. The watch rewrites only on
 * a status change — ten identical answers from a `running` run would hand the
 * row ten new identities and re-render the feed each time. Refresh rewrites
 * unconditionally: the press is the ask.
 *
 * The names on the cast come off the row already drawn — the record carries
 * ids, the project's characters are not in scope here, and a run's cast does
 * not change after it is planned.
 */
export function patchFeedRows(
  client: QueryClient,
  filters: QueryFilters,
  records: RunRecord[],
  when: (row: RunFeedRow, record: RunRecord) => boolean,
) {
  const byId = new Map(records.map((record) => [record.id, record]));
  client.setQueriesData<InfiniteData<RunFeedPage>>(filters, (current) => {
    if (!current) return current;
    let changed = false;
    const pages = current.pages.map((page) => {
      let touched = false;
      const runs = page.runs.map((row) => {
        const record = byId.get(row.id);
        if (!record || !when(row, record)) return row;
        touched = changed = true;
        return rowOfRecord(record, row.cast);
      });
      return touched ? { ...page, runs } : page;
    });
    return changed ? { ...current, pages } : current;
  });
}

/** Every feed the app holds, whatever project and filters it was read for. */
export const FEED_QUERIES: QueryFilters = { queryKey: ["runs", "feed"] };
