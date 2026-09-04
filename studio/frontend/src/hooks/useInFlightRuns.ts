import { useMemo, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { RunFeedPage } from "../types";
import { inFlight } from "../components/run/feedTime";

/**
 * Which projects have a run out right now, read off the feed's own cache.
 *
 * **Nothing cheap answers this from the API** — `ProjectSummary.counts` has no
 * `running`, and `GET /api/runs?status=` is one request per project — so
 * this asks the cache instead. Every feed page lives under
 * `["runs", "feed", <project>, …]` and the feed polls while any row in it can
 * still move, so the cache is fresh for exactly the projects a person has
 * open. Which is the one case the mockup draws: the project being worked in
 * shows "1 running" in its header and a spinner beside its name in the
 * sidebar. A project nobody has opened this session reads as zero, which is
 * an honest "not known" rather than a claim.
 *
 * A run is counted once however many filtered pages hold it — the same row
 * sits under several keys when a filter has been changed.
 */
export function useInFlightRuns(): Record<string, number> {
  const client = useQueryClient();
  const cache = client.getQueryCache();

  // `useSyncExternalStore` compares snapshots by identity, so the snapshot is
  // a string — one that only changes when the answer does.
  const snapshot = useSyncExternalStore(
    (onChange) => cache.subscribe(onChange),
    () => {
      const seen = new Map<string, Set<string>>();
      for (const query of cache.findAll({ queryKey: ["runs", "feed"] })) {
        const project = query.queryKey[2];
        if (typeof project !== "string") continue;
        const data = query.state.data as { pages?: RunFeedPage[] } | undefined;
        for (const page of data?.pages ?? []) {
          for (const run of page.runs) {
            if (!inFlight(run.status)) continue;
            let runs = seen.get(project);
            if (!runs) seen.set(project, (runs = new Set()));
            runs.add(run.id);
          }
        }
      }
      return [...seen.entries()]
        .map(([project, runs]) => `${project}=${runs.size}`)
        .sort()
        .join("&");
    },
    () => "",
  );

  return useMemo(() => {
    const counts: Record<string, number> = {};
    if (!snapshot) return counts;
    for (const pair of snapshot.split("&")) {
      const [project, count] = pair.split("=");
      if (project && count) counts[project] = Number(count);
    }
    return counts;
  }, [snapshot]);
}
