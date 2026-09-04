import { act, cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it } from "vitest";

import type { RunFeedPage } from "../types";
import { useInFlightRuns } from "./useInFlightRuns";

function Probe() {
  const counts = useInFlightRuns();
  return <output data-testid="counts">{JSON.stringify(counts)}</output>;
}

function page(project: string, runs: Array<[string, RunFeedPage["runs"][number]["status"]]>): { pages: RunFeedPage[] } {
  return {
    pages: [
      {
        cursor: null,
        runs: runs.map(([id, status]) => ({ id, project, status }) as RunFeedPage["runs"][number]),
      },
    ],
  };
}

afterEach(cleanup);

/**
 * Counts off the feed's cache, per project, each run once — the same row sits
 * under several keys once a filter has been changed, and a run counted twice
 * would say "2 running" about one prediction.
 */
it("counts the runs in flight per project off the feed cache, deduplicated across filtered pages", () => {
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>,
  );
  expect(screen.getByTestId("counts").textContent).toBe("{}");

  act(() => {
    client.setQueryData(["runs", "feed", "proj-1", { status: "" }], page("proj-1", [["run-a", "running"], ["run-b", "succeeded"], ["run-c", "pending"]]));
    client.setQueryData(["runs", "feed", "proj-1", { status: "running" }], page("proj-1", [["run-a", "running"]]));
    client.setQueryData(["runs", "feed", "proj-2", { status: "" }], page("proj-2", [["run-d", "succeeded"]]));
    // Not the feed: a listing page under another key says nothing here.
    client.setQueryData(["runs", "list", "proj-3"], { runs: [{ id: "run-e", status: "running" }], cursor: null });
  });

  expect(JSON.parse(screen.getByTestId("counts").textContent ?? "{}")).toEqual({ "proj-1": 2 });

  act(() => {
    client.setQueryData(["runs", "feed", "proj-1", { status: "" }], page("proj-1", [["run-a", "succeeded"], ["run-b", "succeeded"], ["run-c", "failed"]]));
    client.setQueryData(["runs", "feed", "proj-1", { status: "running" }], page("proj-1", []));
  });
  expect(screen.getByTestId("counts").textContent).toBe("{}");
});
