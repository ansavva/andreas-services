import { useEffect, useMemo } from "react";
import {
  useQueries,
  useQueryClient,
  type InfiniteData,
  type QueryKey,
} from "@tanstack/react-query";

import { getRun } from "../apis/studio";
import { inFlight } from "../components/run/feedTime";
import { rowOfRecord } from "../components/run/rowOfRecord";
import { isTerminal, type RunFeedPage, type RunFeedRow, type RunRecord } from "../types";

/** How often a run that is still out is asked about. */
export const RUN_WATCH_MS = 5_000;

/**
 * Watch the runs that can still move, and patch them into the feed's cache.
 *
 * **The feed itself does not poll, and this is why.** It used to: the infinite
 * query carried a `refetchInterval` that fired while any row in it was in
 * flight. React Query refetches an infinite query by re-running *every page it
 * holds*, so a feed scrolled to three pages made three `?view=feed` calls every
 * five seconds — and each call re-read an envelope per row and re-signed every
 * send and every output on it — to learn that one run had gone from `running`
 * to `succeeded`. The cost scaled with how far the person had scrolled, which
 * is the opposite of what it should do.
 *
 * So the poll is per run instead: one `GET /api/runs/<id>` per row still out,
 * usually one or two, each reading one envelope. When a watched run's status
 * changes, the row is rebuilt from the record and written into the cached pages
 * in place — the landed outputs arrive in the same response that reports the
 * landing, so nothing re-reads the page the run sits on.
 *
 * **The key is `["run", <id>]` on purpose.** It is the opened run's own key, so
 * a run watched from the feed and read in the lightbox is one request, not two.
 */
export function useRunWatch(feedKey: QueryKey, rows: RunFeedRow[]) {
  const client = useQueryClient();

  // Joined, so the query list is stable while the same runs are out — `rows` is
  // a fresh array on every render of the feed.
  const watching = useMemo(
    () =>
      rows
        .filter((row) => inFlight(row.status))
        .map((row) => row.id)
        .join(","),
    [rows],
  );

  const results = useQueries({
    queries: (watching ? watching.split(",") : []).map((id) => ({
      queryKey: ["run", id],
      queryFn: () => getRun(id),
      refetchInterval: (query: { state: { data: RunRecord | undefined } }) =>
        query.state.data && !isTerminal(query.state.data.status)
          ? RUN_WATCH_MS
          : (false as const),
    })),
  });

  const records = results
    .map((result) => result.data)
    .filter((data): data is RunRecord => Boolean(data));

  // What the effect reacts to. `records` is a new array every render, and the
  // id and status are all a patch depends on — reacting to the array itself
  // would rewrite the cache on every render.
  const landed = records
    .map((record) => `${record.id}:${record.status}`)
    .join(",");

  useEffect(() => {
    if (!landed) return;
    const byId = new Map(records.map((record) => [record.id, record]));

    client.setQueryData<InfiniteData<RunFeedPage>>(feedKey, (current) => {
      if (!current) return current;
      let changed = false;
      const pages = current.pages.map((page) => {
        let touched = false;
        const runs = page.runs.map((row) => {
          const record = byId.get(row.id);
          // Only the status moving is worth a rewrite: a `running` run polled
          // ten times is ten identical answers, and writing each one back would
          // hand every row a new identity and re-render the whole feed.
          if (!record || record.status === row.status) return row;
          touched = changed = true;
          // The names come off the row the feed already drew — the record
          // carries cast ids, the project's characters are not in scope here,
          // and a run's cast does not change after it is planned.
          return rowOfRecord(record, row.cast);
        });
        return touched ? { ...page, runs } : page;
      });
      return changed ? { ...current, pages } : current;
    });
    // `records` is derived from `landed`; listing it would fire every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, feedKey, landed]);
}
