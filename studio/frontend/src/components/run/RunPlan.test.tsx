import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../apis/studio", () => ({
  approveRun: vi.fn(),
  submitRun: vi.fn(),
}));

import { approveRun, submitRun } from "../../apis/studio";
import { ApiError } from "../../apis/client";
import { InFlightBar, RunBar, RunPlan } from "./RunPlan";
import type { RunRecord, RunSend } from "../../types";

/**
 * The Plan section and the run bar.
 *
 * What these hold up is the part that is easy to get subtly wrong in a way
 * nobody notices: that a reconstructed plan says so, that an image's provenance
 * is drawn rather than reduced back to the field name — which is all `bindings`
 * could ever say — and that the one control leading to money takes two presses
 * and writes an approval before it sends anything.
 */

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

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
    sends: [],
    plan: null,
    plan_digest: "sha256:abc",
    approval: null,
    stale: false,
    payload: { prompt: null, request: null, response: null },
    ...over,
  } as RunRecord;
}

describe("the plan", () => {
  it("shows the prompt a person wrote and the parameters they chose", () => {
    render(
      <RunPlan
        run={record({
          plan: {
            version: 1,
            origin: "authored",
            prompt: "a porch at dawn",
            params: { aspect_ratio: "9:16", quality: "high" },
          },
        })}
        onView={vi.fn()}
      />,
    );

    expect(screen.getByText(/a porch at dawn/)).toBeTruthy();
    expect(screen.getByText("aspect_ratio")).toBeTruthy();
    // **Once, in the params row — and this used to assert twice.** A badge at
    // the top of the section repeated it, on the reasoning that aspect ratio is
    // the parameter people scan for and repeating it costs less than making
    // them hunt. In place it read as a label for the whole plan rather than as
    // one setting among several — a bare `3:2` under the heading, next to
    // nothing that said what it was.
    expect(screen.getAllByText("9:16")).toHaveLength(1);
  });

  it("says when a plan was reconstructed rather than written", () => {
    /**
     * A reconstructed plan is not a person's words about their own intent — it
     * is what the recorded request implies about it. A reader deciding whether
     * to trust a detail needs to know which they are looking at, so it is a
     * badge and a sentence rather than something inferred from a missing note.
     */
    render(
      <RunPlan
        run={record({
          plan: { version: 1, origin: "backfilled", prompt: "x", params: {} },
        })}
        onView={vi.fn()}
      />,
    );

    expect(screen.getByText("reconstructed")).toBeTruthy();
    expect(screen.getByText(/Rebuilt from the request/)).toBeTruthy();
  });

  it("draws where each image came from, not just which field it went to", () => {
    /**
     * The whole reason `SEND#` rows exist. `bindings` said six images went to
     * `image_input`; it could not say four were a character's face references
     * and two were frames off an earlier run.
     */
    render(
      <RunPlan
        run={record({
          sends: [
            send({
              order: 1,
              source: { kind: "character", character: "char-1", group: "face" },
            }),
            send({
              order: 2,
              node: "node-2",
              source: { kind: "run", run: "run-0", output: 2 },
            }),
            send({
              order: 3,
              node: "node-3",
              source: { kind: "input-pool", project: "proj-1", position: 4 },
            }),
          ],
        })}
        onView={vi.fn()}
      />,
    );

    expect(screen.getByText("character · face")).toBeTruthy();
    expect(screen.getByText("earlier run · #2")).toBeTruthy();
    expect(screen.getByText("input 4")).toBeTruthy();
  });

  it("groups a start frame apart from the references", () => {
    render(
      <RunPlan
        run={record({
          sends: [
            send({
              order: 1,
              field: "start_image",
              role: "start",
              node: "node-s",
            }),
            send({ order: 2, node: "node-r" }),
          ],
        })}
        onView={vi.fn()}
      />,
    );

    expect(screen.getByText("Start frame")).toBeTruthy();
    expect(screen.getByText("References")).toBeTruthy();
  });

  it("says so plainly when a run predates the plan entirely", () => {
    render(<RunPlan run={record()} onView={vi.fn()} />);

    expect(screen.getByText(/predates the plan/)).toBeTruthy();
  });
});

/**
 * **The control that spends money — one act, two presses, and no dialog.**
 *
 * The app could not submit at all until generation moved into the API, and when
 * it could, it asked twice: a dialog to approve, then a separate Submit button.
 * That was modelled on `runs approve` + `runs submit`, but the CLI's ordinary
 * gesture is `studio run`, which drafts, approves and submits in one — so the
 * page was asking for the same yes under two words, and a second confirm on the
 * thing that matters is what teaches somebody to click through the first.
 *
 * **Nothing mechanical was dropped with it**, and these cases are what says so:
 * the approval row is still written, with the digest of the payload the page is
 * rendering, and a refusal of it sends nothing. The old suite's argument about
 * the states the Submit button must be absent from is answered structurally now
 * — a run that has gone out renders no button at all.
 */
describe("the run bar", () => {
  const bar = { onRan: vi.fn(), onReload: vi.fn() };
  const approve = vi.mocked(approveRun);
  const submit = vi.mocked(submitRun);

  /**
   * The bar holds exactly one button, so it is found by role rather than by
   * label — the label is the thing that changes between the two presses, and a
   * matcher on it would have to know both halves of what is under test.
   */
  function press(times: number) {
    for (let i = 0; i < times; i += 1) {
      fireEvent.click(screen.getByRole("button"));
    }
  }

  it("is a button, and says what it will send on hover", async () => {
    /**
     * **This used to assert the sentence beside the button**, back when three
     * of them framed it: what it sends, that one press arms and the second
     * runs, and that the run closes itself. The payload they described is on
     * the page already, so the explanation moved onto the control — where it
     * is read by hovering or by tabbing to it, which is what `aria-describedby`
     * on the trigger is for. What stays visible without asking is the cost, and
     * it appears on the armed press.
     */
    render(
      <RunBar run={record({ status: "draft", sends: [send()] })} {...bar} />,
    );

    const button = screen.getByRole("button", { name: "Run" });
    fireEvent.focus(button);

    expect(
      await screen.findByText(/1 image above, in that order/),
    ).toBeTruthy();
    expect(button.getAttribute("aria-describedby")).toBeTruthy();
  });

  it("says it spends only once it is armed", () => {
    render(<RunBar run={record({ status: "draft" })} {...bar} />);

    expect(screen.queryByRole("button", { name: /this spends/ })).toBeNull();
    press(1);
    expect(screen.getByRole("button", { name: /this spends/ })).toBeTruthy();
  });

  it("arms on the first press and calls nothing", () => {
    /**
     * The confirmation is the button changing under your finger. It is not a
     * formality either — the arming expires, and moving focus away or pressing
     * Escape takes it back, which `ConfirmDeleteButton` establishes and this
     * borrows wholesale.
     */
    render(<RunBar run={record({ status: "draft" })} {...bar} />);

    press(1);

    expect(approve).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Press again/ })).toBeTruthy();
  });

  it("approves the payload on screen, then submits it, in that order", async () => {
    /**
     * **The digest is the one off the record this page loaded** — never
     * recomputed here. `plan_digest` has had three implementations in this
     * repository and one of them silently disagreed; a client that derived its
     * own would be a fourth.
     */
    const order: string[] = [];
    const sent = record({ status: "running" });
    approve.mockImplementation(async () => {
      order.push("approve");
      return record({ status: "approved" });
    });
    submit.mockImplementation(async () => {
      order.push("submit");
      return sent;
    });

    const onRan = vi.fn();
    render(
      <RunBar
        run={record({ status: "draft", plan_digest: "sha256:abc" })}
        {...bar}
        onRan={onRan}
      />,
    );

    press(2);

    await waitFor(() => expect(order).toEqual(["approve", "submit"]));
    expect(approve).toHaveBeenCalledWith("run-1", "sha256:abc");
    expect(onRan).toHaveBeenCalledWith(sent);
  });

  it("sends nothing when the approval is refused, and says why inline", async () => {
    /**
     * The failure hard rule #2 names, and the reason the digest exists: the plan
     * moved after this page drew it — in another tab, or from a terminal — so
     * the yes on offer is a yes to something nobody here has read.
     *
     * **The API's own sentence, not its code.** `support.structured` answers
     * both; printing `stale_digest` at a person is what the `code`/`message`
     * split exists to stop. The code only decides what to add.
     */
    approve.mockRejectedValue(
      new ApiError(
        "The plan changed after it was approved.",
        409,
        "stale_digest",
      ),
    );
    const onReload = vi.fn();
    render(
      <RunBar run={record({ status: "draft" })} {...bar} onReload={onReload} />,
    );

    press(2);

    await waitFor(() =>
      expect(screen.getByText(/changed after it was approved/)).toBeTruthy(),
    );
    expect(submit).not.toHaveBeenCalled();
    expect(onReload).toHaveBeenCalled();
    expect(screen.queryByText("stale_digest")).toBeNull();
  });

  it("offers no run at all once one has gone out", () => {
    /**
     * Structural rather than disabled. A run row records ONE submission — its
     * request, its response, its outputs — so there is nothing to press here;
     * what a submitted run offers instead is `RunAgainButton`, which makes a
     * second run.
     */
    render(<RunBar run={record({ status: "running" })} {...bar} />);

    expect(screen.queryByRole("button", { name: /run/i })).toBeNull();
  });

  it("keeps saying who approved a run after it went out", () => {
    render(
      <RunBar
        run={record({
          status: "succeeded",
          approval: {
            by: "sub-1",
            at: "2026-08-20T00:00:00Z",
            digest: "sha256:abc",
            via: "relayed",
          },
        })}
        {...bar}
      />,
    );

    expect(screen.getByText(/Approved by sub-1/)).toBeTruthy();
    // A relayed yes was given elsewhere and passed on by an agent. It reads as
    // the weaker claim it is, or the row is indistinguishable from a person
    // pressing the button.
    expect(screen.getByText(/Relayed/)).toBeTruthy();
  });

  it("names the backfill rather than pretending a person approved it", () => {
    /**
     * Nobody approved a run made last August in a browser. The stamp names
     * the mechanism so a future reader can tell the difference, which a row
     * carrying somebody's sub could not.
     */
    render(
      <RunBar
        run={record({
          status: "succeeded",
          approval: {
            by: "backfill",
            at: "2026-08-01T00:00:00Z",
            digest: "sha256:abc",
          },
        })}
        {...bar}
      />,
    );

    expect(screen.getByText(/before approvals were recorded/)).toBeTruthy();
  });

  /* Whether the bar is drawn at all while the plan is being edited is the page's
     decision, not this component's — `RunPage.test.tsx` holds it up. */
});

describe("a run that has gone out and not come back", () => {
  const noop = { onReconcile: vi.fn(), busy: false, error: null };

  it("says the page is watching, so the tab can be closed", () => {
    /**
     * The state that did not exist while the CLI held the lifecycle in one
     * blocking command. A generation is closed by a callback now, so leaving is
     * safe — and a person has to be told that rather than left to guess.
     */
    render(
      <InFlightBar
        run={record({ status: "running", prediction_id: "p-1" })}
        {...noop}
      />,
    );

    expect(screen.getByText(/closing the tab changes nothing/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Check now/ })).toBeTruthy();
  });

  it("offers no check for a run that never named a prediction", () => {
    /** Nothing reached the provider, so there is nothing to ask about. */
    render(
      <InFlightBar
        run={record({ status: "running", prediction_id: null })}
        {...noop}
      />,
    );

    expect(screen.queryByRole("button", { name: /Check now/ })).toBeNull();
    expect(screen.getByText(/named no prediction/i)).toBeTruthy();
  });

  it("shows nothing at all for a run that is not in flight", () => {
    const { container } = render(
      <InFlightBar run={record({ status: "succeeded" })} {...noop} />,
    );

    expect(container.textContent).toBe("");
  });
});
