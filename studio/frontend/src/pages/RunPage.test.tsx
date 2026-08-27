import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { RunRecord } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../apis/studio", () => ({
  getRun: vi.fn(),
  getNodeText: vi.fn(),
  getProject: vi.fn().mockResolvedValue({ id: "proj-1", slug: "a-project", title: "A project" }),
}));

import { getRun } from "../apis/studio";
import { RunPage } from "./RunPage";

const read = vi.mocked(getRun);

const PROJECT = "proj-1";
const RUN = "run-1";

function record(over: Partial<RunRecord> = {}): RunRecord {
  return {
    id: RUN,
    project: PROJECT,
    status: "succeeded",
    kind: "image",
    model: "a-model",
    engine: "replicate",
    prediction_id: null,
    created: "2026-08-20T00:00:00Z",
    submitted: null,
    completed: null,
    cost: null,
    error: null,
    outputs: [],
    scenes: [],
    derived: [],
    bindings: {},
    lineage: { from_run: null, from_output: null },
    payload: { prompt: null, request: null, response: null },
    ...over,
  } as RunRecord;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

beforeEach(() => {
  vi.clearAllMocks();
});

async function open() {
  render(
    <MemoryRouter initialEntries={[`/p/${PROJECT}/r/${RUN}`]}>
      <Routes>
        <Route path="/p/:projectId/r/:runId" element={<RunPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByText("Outputs");
}

/**
 * A run is an async job, and this page used to be a snapshot of one.
 *
 * It showed whatever the status was when it opened and waited for a human to
 * reload — on the one screen whose whole subject changes underneath you.
 */
it("keeps asking while the run can still change", async () => {
  read.mockResolvedValue(record({ status: "running" }));
  await open();

  const first = read.mock.calls.length;
  // Long enough to cross the 5s interval without a fake clock, which React
  // Query's own timers do not cooperate with cleanly.
  await waitFor(() => expect(read.mock.calls.length).toBeGreaterThan(first), { timeout: 7000 });
}, 12_000);

it("stops asking once the run has finished", async () => {
  read.mockResolvedValue(record({ status: "succeeded" }));
  await open();

  const settled = read.mock.calls.length;
  await new Promise((resolve) => setTimeout(resolve, 6500));
  // `succeeded` is terminal — see `TERMINAL_RUN_STATUSES`, which the backend
  // owns and this mirrors. A page that kept polling a finished run would be a
  // request every five seconds, for ever, on every open tab.
  expect(read.mock.calls.length).toBe(settled);
}, 12_000);

/**
 * The breadcrumb reads the project's NAME.
 *
 * A run carries its project's id and nothing else, so the name is a request —
 * worth one, because a button that says "Project" is a way back while a crumb
 * that says which project is also an answer to "where am I".
 */
it("names the project in the trail", async () => {
  read.mockResolvedValue(record());
  await open();

  await waitFor(() => expect(screen.getByText("A project")).toBeTruthy());
});

/**
 * The way back up, which did not exist.
 *
 * A run arrived at from the reel was a dead end: it knew its project and
 * nothing else, so the scene that used it was reachable only by going back to
 * the project and down the other branch. `by-sk` edge rows answer it now.
 */
it("names the scene that used this run, and goes there", async () => {
  read.mockResolvedValue(
    record({ scenes: [{ id: "scene-9", slug: "a-scene", title: "A scene" }] } as Partial<RunRecord>),
  );
  await open();

  const link = await screen.findByRole("button", { name: "A scene" });
  expect(screen.getByText("Used in")).toBeTruthy();
  expect(link).toBeTruthy();
});

it("says nothing at all when no scene has used it", async () => {
  read.mockResolvedValue(record());
  await open();

  // The ordinary case — most runs are never cut into anything, so a permanent
  // "Used in: —" would be noise on almost every run in the library.
  expect(screen.queryByText("Used in")).toBeNull();
});
