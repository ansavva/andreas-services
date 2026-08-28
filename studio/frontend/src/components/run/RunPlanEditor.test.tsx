import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunPlanEditor } from "./RunPlanEditor";
import { TestProviders } from "../../test-providers";
import type { RunPlan, RunRecord, RunSend } from "../../types";

/**
 * Editing a draft.
 *
 * What these hold up is the part a screenshot cannot: that **only the half that
 * moved is written**. Each `PATCH` is a full replace of its half, so a save that
 * sent both every time would rewrite the send rows of a run whose prompt was the
 * only thing touched — and every rewrite of either half clears the approval, so
 * the cost of the extra call is a yes withdrawn for nothing.
 */

const patchRunPlan = vi.fn();
const patchRunSends = vi.fn();

vi.mock("../../apis/studio", () => ({
  patchRunPlan: (...args: unknown[]) => patchRunPlan(...args),
  patchRunSends: (...args: unknown[]) => patchRunSends(...args),
  // The picker's listing call. Named here because the mock replaces the whole
  // module, and an unmocked `getTree` would be `undefined` the moment the dialog
  // opens rather than at import.
  getTree: vi.fn(() =>
    Promise.resolve({ folders: [], files: [], breadcrumbs: [], sort: "name" }),
  ),
  getAsset: vi.fn(() => Promise.resolve({ url: "https://example.test/re-signed" })),
  // Read for its `root`, which is where the picker opens.
  getProject: vi.fn(() => Promise.resolve({ id: "proj-1", root: "node-project" })),
}));

afterEach(() => {
  cleanup();
  patchRunPlan.mockReset();
  patchRunSends.mockReset();
});

function send(over: Partial<RunSend> = {}): RunSend {
  return {
    order: 1,
    field: "image_input",
    role: "reference",
    node: "node-1",
    name: "front.webp",
    url: "https://example.test/front.webp",
    source: { kind: "object" },
    ...over,
  } as RunSend;
}

function draft(over: Partial<RunRecord> = {}): RunRecord {
  return {
    id: "run-1",
    project: "proj-1",
    status: "draft",
    kind: "image",
    model: "a-model",
    engine: "replicate",
    created: "2026-08-20T00:00:00Z",
    folder: "node-folder",
    outputs: [],
    scenes: [],
    derived: [],
    bindings: {},
    sends: [send(), send({ order: 2, node: "node-2", name: "profile.webp" })],
    plan: {
      version: 1,
      origin: "authored",
      prompt: "a porch at dawn",
      params: { aspect_ratio: "9:16" },
      note: null,
    },
    plan_digest: "sha256:abc",
    approval: null,
    stale: false,
    lineage: { from_run: null, from_output: null },
    payload: { prompt: null, request: null, response: null },
    ...over,
  } as RunRecord;
}

/** The plan body of the first `PATCH /plan` — read after asserting it was called. */
function planSent(): RunPlan {
  const [, plan] = patchRunPlan.mock.calls[0] ?? [];
  return plan as RunPlan;
}

/** The sends body of the first `PATCH /sends`. */
function sendsSent(): { field: string; role: string | null; node: string }[] {
  const [, sends] = patchRunSends.mock.calls[0] ?? [];
  return sends as { field: string; role: string | null; node: string }[];
}

function editor(run = draft(), onSaved = vi.fn()) {
  render(
    <TestProviders>
      <RunPlanEditor run={run} onSaved={onSaved} onCancel={vi.fn()} />
    </TestProviders>,
  );
  return onSaved;
}

describe("editing a plan", () => {
  it("writes the plan and leaves the images alone", async () => {
    patchRunPlan.mockResolvedValue(draft());
    const onSaved = editor();

    fireEvent.change(screen.getByLabelText("Prompt"), {
      target: { value: "a porch at dusk" },
    });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().prompt).toBe("a porch at dusk");
    expect(patchRunSends).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalled();
  });

  it("writes the images and leaves the plan alone", async () => {
    patchRunSends.mockResolvedValue(draft());
    editor();

    fireEvent.click(screen.getByLabelText("Move image 2 earlier"));
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunSends).toHaveBeenCalled());
    expect(patchRunPlan).not.toHaveBeenCalled();
    expect(sendsSent().map((each) => each.node)).toEqual(["node-2", "node-1"]);
  });

  it("writes nothing at all when nothing was touched", async () => {
    editor();

    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).not.toHaveBeenCalled());
    expect(patchRunSends).not.toHaveBeenCalled();
  });

  it("removes an image", async () => {
    patchRunSends.mockResolvedValue(draft());
    editor();

    fireEvent.click(screen.getByLabelText("Remove image 1"));
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunSends).toHaveBeenCalled());
    expect(sendsSent()).toHaveLength(1);
    expect(sendsSent()[0]?.node).toBe("node-2");
  });

  it("stores a number as a number and everything else as text", async () => {
    /**
     * The one place this form guesses, so it is the one place worth pinning: a
     * model that takes `duration: 8` and is handed `"8"` is a payload the
     * provider rejects, and `png` must not become anything other than `png`.
     */
    patchRunPlan.mockResolvedValue(draft());
    editor();

    fireEvent.click(screen.getByText("Add a parameter"));
    fireEvent.change(screen.getByLabelText("Parameter 2 name"), {
      target: { value: "duration" },
    });
    fireEvent.change(screen.getByLabelText("Parameter 2 value"), { target: { value: "8" } });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().params).toEqual({ aspect_ratio: "9:16", duration: 8 });
  });

  it("keeps a reconstructed plan reconstructed", async () => {
    /**
     * `PATCH /plan` replaces the plan whole, so anything not carried through is
     * dropped. A backfilled plan quietly becoming an authored one would be a
     * record claiming somebody wrote words that were read off a request
     * document — and the run page says which it is.
     */
    patchRunPlan.mockResolvedValue(draft());
    editor(draft({ plan: { version: 1, origin: "backfilled", prompt: "a porch", params: {} } }));

    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "a porch at noon" } });
    fireEvent.click(screen.getByText("Save the plan"));

    await waitFor(() => expect(patchRunPlan).toHaveBeenCalled());
    expect(planSent().origin).toBe("backfilled");
  });

  it("refuses to save a structured prompt that stopped being JSON", async () => {
    editor(
      draft({
        plan: {
          version: 1,
          origin: "authored",
          prompt: { shot: "a porch at dawn" },
          params: {},
        },
      }),
    );

    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "{ shot: " } });
    fireEvent.click(screen.getByText("Save the plan"));

    expect(await screen.findByText(/not valid JSON/)).toBeTruthy();
    expect(patchRunPlan).not.toHaveBeenCalled();
    expect(patchRunSends).not.toHaveBeenCalled();
  });

  it("says that saving withdraws the approval, before anything is typed", () => {
    editor();

    expect(screen.getByText("withdraws the approval")).toBeTruthy();
  });
});
