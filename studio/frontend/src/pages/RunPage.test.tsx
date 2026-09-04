import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunRecord, RunStatus, RunSummary } from "../types";
import { TestProviders } from "../test-providers";

vi.mock("../apis/studio", () => ({
  getRun: vi.fn(),
  getNodeText: vi.fn(),
  // A draft's payload tab asks the API what it would send — see
  // `PayloadPreview`. Unmocked it hangs the poll test for its whole timeout.
  getRunPayloadPreview: vi
    .fn()
    .mockResolvedValue({ request: {}, prompt: null }),
  // `characters` included: the plan editor reads its length to decide whether
  // to fall back to the whole library, and a project shape missing it crashed
  // the editor rather than the crumb that asks for the name.
  getProject: vi.fn().mockResolvedValue({
    id: "proj-1",
    name: "A project",
    characters: [],
  }),
  getCharacters: vi.fn().mockResolvedValue([]),
  // "Has this exact payload already gone out here" — see `DuplicateNotice`.
  // Empty unless a case says otherwise.
  getRuns: vi.fn().mockResolvedValue({ runs: [], cursor: null }),
  deleteRun: vi.fn().mockResolvedValue({ id: "run-1", files: "keep" }),
  // The cast editor and the template picker, both mounted by `RunPlanEditor`.
  // Unmocked they are `undefined` at the first render, and a `useResource`
  // handed `undefined` never settles — which does not fail the suite, it hangs
  // it and then the runner is killed.
  setRunCharacters: vi.fn().mockResolvedValue({}),
  getTemplates: vi.fn().mockResolvedValue({ blocks: {}, templates: [] }),
  submitRun: vi.fn(),
  reconcileRun: vi.fn(),
  patchRunPlan: vi.fn(),
  patchRunSends: vi.fn(),
  // The editor asks the registry what this model takes, and degrades when it
  // cannot — rejected here, which is the path this file exercises.
  getModel: vi.fn().mockRejectedValue(new Error("no registry in tests")),
  getModelSchema: vi.fn().mockRejectedValue(new Error("no registry in tests")),
  getCharacterSelection: vi.fn(),
  // `PromotePanel`'s four primitives. Present for the same reason as the two
  // above: an accessed name that is not on the factory is a vitest error about
  // the mock, which reads as a bug in the page.
  getCharacter: vi.fn(),
  getFolder: vi.fn(),
  createNode: vi.fn(),
  copyNodes: vi.fn(),
}));

import { deleteRun, getRun, getRuns } from "../apis/studio";
import { RunPage } from "./RunPage";

const read = vi.mocked(getRun);
const listRuns = vi.mocked(getRuns);
const remove = vi.mocked(deleteRun);

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
    bindings: {},
    // The authored half. Present on every response the API gives — `get_run`
    // always writes these three keys, `null` included, so a client never has to
    // tell "absent" from "cleared".
    sends: [],
    plan: null,
    payload: { prompt: null, request: null, response: null },
    ...over,
  } as RunRecord;
}

/** A listing row, which is what `?fingerprint=` answers with. */
function summary(id: string, status: RunStatus): RunSummary {
  return {
    id,
    project: PROJECT,
    status,
    kind: "image",
    model: "a-model",
    created: "2026-08-19T00:00:00Z",
    cost: null,
    thumb: null,
    fingerprint: "fp-1",
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

beforeEach(() => {
  vi.clearAllMocks();
});

async function open(state?: { editing?: boolean }) {
  render(
    <MemoryRouter
      initialEntries={[{ pathname: `/p/${PROJECT}/r/${RUN}`, state }]}
    >
      <Routes>
        <Route path="/p/:projectId/r/:runId" element={<RunPage />} />
        <Route path="/p/:projectId" element={<div>the project page</div>} />
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
  await waitFor(() => expect(read.mock.calls.length).toBeGreaterThan(first), {
    timeout: 7000,
  });
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
    record({
      scenes: [{ id: "scene-9", name: "A scene" }],
    } as Partial<RunRecord>),
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

/**
 * **What this page lets a person DO, which until now was read it.**
 *
 * Three controls, and which of them exists is decided by one thing: whether the
 * run has been sent. An unsubmitted run can still be run or thrown away; a sent
 * one can only be run again, as a second run. Nothing lets a submitted run be
 * re-sent — a run row records one submission.
 */
const again = () => screen.queryByRole("button", { name: /run again/i });
/** Behind the page bar's `⋯` now — see `menuTrigger`. */
const menuTrigger = () => screen.queryByRole("button", { name: "More actions" });

it("offers Run again only once a run has been sent", async () => {
  read.mockResolvedValue(record({ status: "succeeded" }));
  await open();

  expect(again()).toBeTruthy();
});

it("offers no Run again on a run that has not gone out", async () => {
  /**
   * A draft has its own control — the one-act Run — and offering both would be
   * two buttons that spend, one of which quietly makes a second run first.
   */
  read.mockResolvedValue(record({ status: "draft" }));
  await open();

  expect(again()).toBeNull();
  // The one-act Run, which is a bare "Run" now — the cost moved to the armed
  // press and the explanation to the tooltip.
  expect(screen.getByRole("button", { name: "Run" })).toBeTruthy();
});

it("offers Discard on an unsubmitted run, and deletes it back to the project", async () => {
  /**
   * `DELETE /api/runs/<id>` has no status gate — the app is what restricts this
   * to runs nothing was spent on. An accidental draft should cost nothing to
   * undo, which is the whole reason drafts are cheap to make.
   */
  read.mockResolvedValue(record({ status: "draft" }));
  await open();

  fireEvent.click(menuTrigger() as HTMLElement);
  const item = screen.getByRole("menuitem", { name: "Delete" });
  // Armed first: the same two-press confirm every destructive control in this
  // app uses, and never a dialog — just a menu item that arms in place, the
  // way `ItemActions`' own delete item does.
  fireEvent.click(item);
  fireEvent.click(screen.getByRole("menuitem", { name: /confirm/i }));

  await waitFor(() => expect(remove).toHaveBeenCalledWith(RUN));
  await screen.findByText("the project page");
});

it("offers no Discard once a run has been sent", async () => {
  read.mockResolvedValue(record({ status: "succeeded" }));
  await open();

  fireEvent.click(menuTrigger() as HTMLElement);
  expect(screen.queryByRole("menuitem", { name: "Delete" })).toBeNull();
});

/**
 * **The Plan/Payload split is a place now, not a reading position.** It used to
 * be `useState` — a pasted link into the payload landed a second reader on
 * Plan, having read none of what the first one meant to share. Every other
 * tab in the app already works this way; this was the one holdout.
 */
it("keeps the open pane in the address, at rest naming none", async () => {
  read.mockResolvedValue(record({ status: "succeeded" }));

  function Probe() {
    const [params] = useSearchParams();
    return <div data-testid="tab-param">{params.get("tab") ?? ""}</div>;
  }

  render(
    <MemoryRouter initialEntries={[`/p/${PROJECT}/r/${RUN}`]}>
      <Routes>
        <Route
          path="/p/:projectId/r/:runId"
          element={
            <>
              <RunPage />
              <Probe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  await screen.findByText("Outputs");

  // The default tab, written as absence — a link copied at rest names no tab.
  expect(screen.getByTestId("tab-param").textContent).toBe("");

  fireEvent.click(screen.getByRole("tab", { name: "Request" }));
  expect(screen.getByTestId("tab-param").textContent).toBe("request");

  fireEvent.click(screen.getByRole("tab", { name: "Plan" }));
  expect(screen.getByTestId("tab-param").textContent).toBe("");
});

/**
 * **The duplicate warning, which is about money rather than about drawing.**
 *
 * A fingerprint is the hash of what would go to the provider, so two runs
 * sharing one are two charges for the same picture. It warns and does not
 * refuse: a model answers differently every time, so a second attempt at the
 * same payload is the ordinary way to get another frame.
 */
it("warns when another run in the project already sent this payload", async () => {
  read.mockResolvedValue(record({ status: "draft", fingerprint: "fp-1" }));
  listRuns.mockResolvedValue({
    runs: [summary(RUN, "draft"), summary("run-0", "succeeded")],
    cursor: null,
  });
  await open();

  expect(await screen.findByText(/has been run here before/)).toBeTruthy();
  // Asked WITH drafts, or the draft being asked about is hidden from its own
  // question.
  expect(listRuns).toHaveBeenCalledWith(
    expect.objectContaining({ fingerprint: "fp-1", include: "drafts" }),
  );
});

it("does not call a run its own duplicate, nor count another draft", async () => {
  /**
   * The run itself shares its own fingerprint by definition, and a second draft
   * cost nothing — nothing was sent for either, so neither is a charge to warn
   * about.
   */
  read.mockResolvedValue(record({ status: "draft", fingerprint: "fp-1" }));
  listRuns.mockResolvedValue({
    runs: [summary(RUN, "draft"), summary("run-9", "draft")],
    cursor: null,
  });
  await open();

  await waitFor(() => expect(listRuns).toHaveBeenCalled());
  expect(screen.queryByText(/has been run here before/)).toBeNull();
});

/**
 * Arriving with the editor already open.
 *
 * The composer strip makes a draft with an empty plan and exists only to be
 * filled in, so landing on its read view — a page saying the run predates the
 * plan, with an Edit button under it — would be a step nobody wants. Carried by
 * the navigation rather than the URL: it describes one arrival, not the page.
 */
it("opens in the editor when the navigation asked for it", async () => {
  read.mockResolvedValue(record({ status: "draft" }));
  await open({ editing: true });

  expect(await screen.findByText("Editing the plan")).toBeTruthy();
  // The armed spend control is hidden behind the form: a Run button beside
  // unsaved words is a yes to whichever of the two you were not looking at.
  expect(screen.queryByRole("button", { name: /this spends/ })).toBeNull();
});

/**
 * **Promote to reference, and only from a picture.**
 *
 * A reference is what every later render of a character is checked against, so a
 * clip cannot be one — the CLI says the same thing by resolving `--from-run`
 * outputs against its image extension set. The control is a SIBLING of the
 * output panel rather than something inside it: the panel's caption is a real
 * `<a href>` and its player is full of buttons, and a button inside an anchor is
 * neither one thing nor the other to a keyboard.
 */
const promote = () => screen.queryByRole("button", { name: /promote/i });

function output(node: string, contentType: string) {
  return {
    node,
    name: node,
    content_type: contentType,
    url: `https://example.invalid/${node}`,
  };
}

it("offers Promote on an image output", async () => {
  read.mockResolvedValue(
    record({ outputs: [output("frame.webp", "image/webp")] }),
  );
  await open();

  expect(promote()).toBeTruthy();
});

it("offers no Promote on a video output", async () => {
  read.mockResolvedValue(record({ outputs: [output("clip.mp4", "video/mp4")] }));
  await open();

  expect(promote()).toBeNull();
});

it("opens the promote panel under the outputs when pressed", async () => {
  read.mockResolvedValue(
    record({
      characters: ["char-1"],
      outputs: [output("frame.webp", "image/webp")],
    }),
  );
  await open();

  fireEvent.click(promote() as HTMLElement);

  // The panel's own sentence — hard rule #2b said before the fact rather than
  // after, in terms of what the reader is deciding rather than of the copy the
  // code makes.
  expect(
    await screen.findByText(/References are the pictures studio works from/i),
  ).toBeTruthy();
});

/**
 * An empty Outputs is three different facts, and saying the wrong one is a lie
 * about whether money was spent.
 *
 * "Nothing came back" is a report on a submission — the run went out, the model
 * answered, and the answer was empty. Said on a draft it tells somebody still
 * writing a plan that their run failed.
 */
describe("what an empty Outputs says", () => {
  it("says a draft has not run", async () => {
    read.mockResolvedValue(record({ status: "draft", outputs: [] }));
    await open();

    expect(screen.getByText("Not run yet.")).toBeTruthy();
  });

  it("says a run in flight is still working", async () => {
    read.mockResolvedValue(
      record({ status: "running", prediction_id: "p-1", outputs: [] }),
    );
    await open();

    expect(screen.getByText("Still working.")).toBeTruthy();
  });

  it("says nothing came back only once something was sent", async () => {
    read.mockResolvedValue(record({ status: "succeeded", outputs: [] }));
    await open();

    expect(screen.getByText("Nothing came back.")).toBeTruthy();
  });
});


it("ignores an editing arrival on a run that has been sent", async () => {
  /** `PATCH /plan` refuses a submitted run; the state describes an intention
   * and the run decides whether it is possible. */
  read.mockResolvedValue(record({ status: "succeeded" }));
  await open({ editing: true });

  expect(screen.queryByText("Editing the plan")).toBeNull();
});
