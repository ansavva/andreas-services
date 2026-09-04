import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  createRun: vi.fn(),
  submitRun: vi.fn(),
}));

import { createRun, submitRun } from "../../apis/studio";
import { RunAgainButton } from "./RunAgainButton";
import { rerunBodyOf } from "./rerun";
import type { CreatedRun, RunRecord } from "../../types";

/**
 * Run again — the whole sequence behind one armed press.
 *
 * **What these pin is the ORDER and the fact that it finishes.** Three things
 * have to happen in one gesture with nothing in between for a person to answer,
 * and two of them can fail independently: create writes a draft, submit spends,
 * and the address moves to the new attempt. There is no approve between them —
 * decision 2026-09-04 — so get the order wrong and the failure is a second
 * charge nobody asked for.
 *
 * Placeholder slugs only (hard rule #1): no character in this library is named
 * in this repository.
 */

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

const create = vi.mocked(createRun);
const submit = vi.mocked(submitRun);

function record(over: Partial<RunRecord> = {}): RunRecord {
  return {
    id: "run-1",
    project: "proj-1",
    status: "succeeded",
    kind: "image",
    model: "a-model",
    engine: "replicate",
    created: "2026-08-20T00:00:00Z",
    outputs: [],
    scenes: [],
    bindings: {},
    sends: [
      {
        order: 1,
        field: "image_input",
        role: "reference",
        node: "node-1",
        name: "front.webp",
      },
    ],
    plan: {
      version: 1,
      origin: "authored",
      prompt: "a porch at dawn",
      params: {},
    },
    payload: { prompt: null, request: null, response: null },
    ...over,
  } as RunRecord;
}

function created(over: Partial<CreatedRun> = {}): CreatedRun {
  return {
    id: "run-2",
    project: "proj-1",
    status: "draft",
    folder: "node-f",
    payload: { prompt: null, request: null, response: null },
    fingerprint: "sha256:fp",
    sends: [],
    created: "2026-08-21T00:00:00Z",
    ...over,
  } as CreatedRun;
}

/** Where the router ended up, as text, so a push is an assertion. */
function Address() {
  const location = useLocation();
  return (
    <>
      <div>at {location.pathname}</div>
      {/* Reported separately so the line above stays one text node — the
          existing cases match it exactly. `Duplicate` hands `editing` to the
          page it opens, and a probe reporting only the path would pass whether
          or not the editor was asked for. */}
      <div data-testid="state">{JSON.stringify(location.state)}</div>
    </>
  );
}

function open(run: RunRecord = record()) {
  render(
    <MemoryRouter initialEntries={["/p/proj-1/r/run-1"]}>
      <RunAgainButton run={run} />
      <Address />
    </MemoryRouter>,
  );
}

/**
 * The bar holds one button, found by role rather than by label: the label is
 * what changes between the two presses, so matching on it would mean knowing
 * both halves of the thing under test.
 */
const button = () => screen.getByRole("button", { name: /Run again|Press again/ });

/**
 * **Duplicate is the other half of "re-run and edit".**
 *
 * `Run again` re-sends a payload byte-identical to the one on screen, which is
 * no use when the run was almost right — and editing a submitted run is refused
 * by the API, correctly, because its plan has to keep describing what was sent.
 * So the way to change a finished run is to make a new one from it, and that
 * path has to cost nothing until somebody runs it.
 */
describe("duplicate", () => {
  const dup = () => screen.getByRole("button", { name: "Duplicate" });

  it("creates a draft and opens it, spending nothing", async () => {
    create.mockResolvedValue(created());
    const source = record();
    open(source);

    fireEvent.click(dup());

    await waitFor(() => expect(create).toHaveBeenCalledWith(rerunBodyOf(source)));
    expect(submit).not.toHaveBeenCalled();
    // The draft opens over the feed; its row there offers Edit and Run. There
    // is no editor page to land in any more — the create bar is the editor.
    expect(await screen.findByText("at /p/proj-1/r/run-2")).toBeTruthy();
  });

  it("opens every clone, not just the first", async () => {
    create.mockResolvedValue(created());
    open();

    fireEvent.click(dup());
    expect(await screen.findByText("at /p/proj-1/r/run-2")).toBeTruthy();

    create.mockResolvedValue(created({ id: "run-3" }));
    fireEvent.click(dup());
    expect(await screen.findByText("at /p/proj-1/r/run-3")).toBeTruthy();
  });

  it("takes one press — there is nothing to arm against", () => {
    // The arm-then-fire gesture exists because the second press spends. This
    // one does not, so a confirm would be a step for its own sake.
    create.mockResolvedValue(created());
    open();

    fireEvent.click(dup());

    expect(create).toHaveBeenCalledTimes(1);
  });

  it("stays put and says why when the draft cannot be made", async () => {
    create.mockRejectedValue(new Error("project is not yours"));
    open();

    fireEvent.click(dup());

    expect(await screen.findByText("project is not yours")).toBeTruthy();
    expect(screen.queryByText("at /p/proj-1/r/run-2")).toBeNull();
  });
});

describe("run again", () => {
  it("does nothing on the first press but say what the second will do", () => {
    /**
     * The same arm-then-fire the one-act Run uses, and for the same reason: this
     * press IS the act, so it cannot be a press somebody made on the way to
     * something else.
     */
    open();

    fireEvent.click(button());

    expect(create).not.toHaveBeenCalled();
    // **This used to assert a sentence beside the button too.** Two paragraphs
    // framed this control — what a re-run copies, where the page goes after —
    // and both are on the tooltip now. What has to stay visible is the cost,
    // and the armed label is where it says so.
    expect(screen.getByRole("button", { name: /Press again/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /this spends/ })).toBeTruthy();
  });

  it("creates the new draft, submits it, then moves the page", async () => {
    /**
     * **Submit is called on the NEW run's id**, the one the API just minted —
     * not the one this page was rendering. Nothing is approved in between.
     */
    const order: string[] = [];
    create.mockImplementation(async () => {
      order.push("create");
      return created();
    });
    submit.mockImplementation(async () => {
      order.push("submit");
      return record({ id: "run-2", status: "running" });
    });

    open();
    fireEvent.click(button());
    fireEvent.click(button());

    // The address is last, so finding it proves both calls resolved first.
    expect(await screen.findByText("at /p/proj-1/r/run-2")).toBeTruthy();
    expect(order).toEqual(["create", "submit"]);
    expect(submit).toHaveBeenCalledWith("run-2");
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "proj-1",
        model: "a-model",
        // Verbatim, including `origin` — see `rerunBodyOf`.
        plan: expect.objectContaining({ origin: "authored" }),
        sends: [{ field: "image_input", role: "reference", node: "node-1" }],
      }),
    );
  });

  it("still lands on the new draft when the submission fails", async () => {
    /**
     * The draft exists, so the draft is the thing to look at. It lands in front
     * of the ordinary run bar, which is the recovery path for exactly this and
     * states the refusal in its own words when pressed.
     */
    create.mockResolvedValue(created());
    submit.mockRejectedValue(new Error("the provider refused"));

    open();
    fireEvent.click(button());
    fireEvent.click(button());

    expect(await screen.findByText("at /p/proj-1/r/run-2")).toBeTruthy();
  });

  it("stays put and says why when nothing was created", async () => {
    /** The one failure that leaves nothing behind to navigate to. */
    create.mockRejectedValue(new Error("that project is gone"));

    open();
    fireEvent.click(button());
    fireEvent.click(button());

    expect(await screen.findByText(/that project is gone/)).toBeTruthy();
    expect(screen.getByText("at /p/proj-1/r/run-1")).toBeTruthy();
  });
});
