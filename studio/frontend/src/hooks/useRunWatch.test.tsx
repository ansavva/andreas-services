import { act, cleanup, render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";

import type { RunFeedPage, RunFeedRow, RunRecord } from "../types";
import { useRunWatch } from "./useRunWatch";

const getRun = vi.hoisted(() => vi.fn());
vi.mock("../apis/studio", () => ({ getRun }));

const KEY = ["runs", "feed", "proj-1", { status: "" }];

function row(id: string, status: RunFeedRow["status"]): RunFeedRow {
  return {
    id,
    project: "proj-1",
    status,
    outputs: [],
    cast: [{ id: "char-1", name: "Ada" }],
  } as unknown as RunFeedRow;
}

function record(id: string, status: RunRecord["status"]): RunRecord {
  return {
    id,
    lib: "lib-1",
    project: "proj-1",
    status,
    kind: "image",
    engine: null,
    model: "m",
    created: "2026-09-09T00:00:00Z",
    submitted: null,
    completed: null,
    error: null,
    cost: null,
    plan: null,
    characters: ["char-1"],
    cast: ["char-1"],
    sends: [],
    outputs: [{ node: "node-1", url: "https://example.test/one.png" }],
  } as unknown as RunRecord;
}

function pages(rows: RunFeedRow[]) {
  return { pages: [{ runs: rows, cursor: null } as RunFeedPage], pageParams: [null] };
}

function Probe({ rows }: { rows: RunFeedRow[] }) {
  useRunWatch(KEY, rows);
  return null;
}

afterEach(() => {
  cleanup();
  getRun.mockReset();
});

/**
 * The point of the hook: the pages are not re-read, the runs that are out are.
 *
 * Three rows, one running — one `GET /api/runs/<id>`, and the feed's own
 * `?view=feed` query is never touched.
 */
it("asks after the runs in flight only, one request each", async () => {
  getRun.mockResolvedValue(record("run-b", "running"));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const rows = [
    row("run-a", "succeeded"),
    row("run-b", "running"),
    row("run-c", "failed"),
  ];
  client.setQueryData(KEY, pages(rows));

  render(
    <QueryClientProvider client={client}>
      <Probe rows={rows} />
    </QueryClientProvider>,
  );

  await waitFor(() => expect(getRun).toHaveBeenCalledTimes(1));
  expect(getRun).toHaveBeenCalledWith("run-b");
});

/** Nothing out, nothing asked. */
it("asks nothing when every row has landed", async () => {
  const client = new QueryClient();
  const rows = [row("run-a", "succeeded"), row("run-b", "draft")];
  client.setQueryData(KEY, pages(rows));

  render(
    <QueryClientProvider client={client}>
      <Probe rows={rows} />
    </QueryClientProvider>,
  );

  await act(async () => {});
  expect(getRun).not.toHaveBeenCalled();
});

/**
 * The landing is written into the page in place — the outputs come back on the
 * same response that reported the new status, so nothing re-reads the feed.
 */
it("patches the landed run into the cached page, keeping the cast's names", async () => {
  getRun.mockResolvedValue(record("run-b", "succeeded"));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const rows = [row("run-a", "succeeded"), row("run-b", "running")];
  client.setQueryData(KEY, pages(rows));

  render(
    <QueryClientProvider client={client}>
      <Probe rows={rows} />
    </QueryClientProvider>,
  );

  await waitFor(() => {
    const held = client.getQueryData(KEY) as ReturnType<typeof pages>;
    expect(held.pages[0]!.runs[1]!.status).toBe("succeeded");
  });

  const held = client.getQueryData(KEY) as ReturnType<typeof pages>;
  const landed = held.pages[0]!.runs[1]!;
  expect(landed.outputs).toHaveLength(1);
  expect(landed.thumb).toEqual({
    node: "node-1",
    url: "https://example.test/one.png",
  });
  // The names are the feed's; the record carries ids only.
  expect(landed.cast).toEqual([{ id: "char-1", name: "Ada" }]);
  // The row that had already landed is untouched — same object, no re-render
  // of a tile whose picture has not changed.
  expect(held.pages[0]!.runs[0]).toBe(rows[0]);
});
