import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApproveBar, InFlightBar, RunPlan } from "./RunPlan";
import type { RunRecord, RunSend } from "../../types";

/**
 * The Plan section and the approve bar.
 *
 * What these hold up is the part that is easy to get subtly wrong in a way
 * nobody notices: that the digest state is stated in WORDS, that a reconstructed
 * plan says so, and that an image's provenance is drawn rather than reduced back
 * to the field name — which is all `bindings` could ever say.
 */

afterEach(cleanup);

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

describe("the approve bar", () => {
  const noop = {
    onApprove: vi.fn(),
    onRevoke: vi.fn(),
    onSubmit: vi.fn(),
    busy: false,
    error: null,
  };

  it("says nobody has approved a draft", () => {
    render(<ApproveBar run={record({ status: "draft" })} {...noop} />);

    expect(screen.getByText(/Nothing has been approved/)).toBeTruthy();
  });

  it("says the payload changed, when it has", () => {
    /**
     * **The sentence the whole mechanism exists to be able to say.** Hard rule
     * #2 says re-approve after any edit; until the digest existed, nothing could
     * tell that an edit had happened after a yes.
     */
    render(
      <ApproveBar
        run={record({ status: "approved", stale: true })}
        {...noop}
      />,
    );

    expect(screen.getByText(/changed after it was approved/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /approve again/i })).toBeTruthy();
  });

  it("offers to revoke an approval that still matches its payload", () => {
    render(
      <ApproveBar
        run={record({
          status: "approved",
          approval: {
            by: "sub-1",
            at: "2026-08-20T00:00:00Z",
            digest: "sha256:abc",
          },
        })}
        {...noop}
      />,
    );

    expect(screen.getByRole("button", { name: "Revoke" })).toBeTruthy();
  });

  it("approves only after the dialog is confirmed", () => {
    /**
     * One click is not an approval. The dialog restates what is being approved —
     * the prompt, the parameters and the images, in order — because hard rule #2
     * is about a person reading a payload, not about a button existing.
     */
    const onApprove = vi.fn();
    render(
      <ApproveBar
        run={record({ status: "draft", sends: [send()] })}
        {...noop}
        onApprove={onApprove}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Approve this payload/ }),
    );
    expect(onApprove).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onApprove).toHaveBeenCalledOnce();
  });

  it("names the backfill rather than pretending a person approved it", () => {
    /**
     * Nobody approved a run made last August in a browser. The stamp names
     * the mechanism so a future reader can tell the difference, which a row
     * carrying somebody's sub could not.
     */
    render(
      <ApproveBar
        run={record({
          status: "succeeded",
          approval: {
            by: "backfill",
            at: "2026-08-01T00:00:00Z",
            digest: "sha256:abc",
          },
        })}
        {...noop}
      />,
    );

    expect(screen.getByText(/before approvals were recorded/)).toBeTruthy();
  });
});

/**
 * **The control that spends money, and the states it must not appear in.**
 *
 * The app could not submit at all until generation moved into the API — the
 * provider credential lived in the CLI, so a run approved on this page then had
 * to be sent from a terminal, and the approve bar said so in as many words.
 *
 * There is deliberately no second confirm dialog on Submit: the approve dialog
 * is where a person reads the payload and says yes, and asking twice teaches
 * somebody to click through the prompt that matters. What stands in for it is
 * that this button exists in exactly one state — so the tests below are mostly
 * about the states it is absent from.
 */
describe("submitting from the app", () => {
  const noop = {
    onApprove: vi.fn(),
    onRevoke: vi.fn(),
    onSubmit: vi.fn(),
    busy: false,
    error: null,
  };
  const approved = {
    status: "approved" as const,
    approval: { by: "sub-1", at: "2026-08-20T00:00:00Z", digest: "sha256:abc" },
  };

  it("offers to submit a run whose approval still matches its payload", () => {
    render(<ApproveBar run={record(approved)} {...noop} />);

    expect(screen.getByRole("button", { name: /Submit/ })).toBeTruthy();
  });

  it("sends nothing until the button is pressed", () => {
    const onSubmit = vi.fn();
    render(<ApproveBar run={record(approved)} {...noop} onSubmit={onSubmit} />);

    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Submit/ }));

    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("does NOT offer to submit an unapproved draft", () => {
    render(<ApproveBar run={record({ status: "draft" })} {...noop} />);

    expect(screen.queryByRole("button", { name: /Submit/ })).toBeNull();
  });

  it("does NOT offer to submit a payload that changed after it was approved", () => {
    /**
     * The failure hard rule #2 names. The API would refuse this with a 409
     * anyway; the button is absent so a person is not invited into a refusal.
     */
    render(<ApproveBar run={record({ ...approved, stale: true })} {...noop} />);

    expect(screen.queryByRole("button", { name: /Submit/ })).toBeNull();
    expect(screen.getByRole("button", { name: /approve again/i })).toBeTruthy();
  });

  it("does NOT offer to submit a run that has already gone out", () => {
    render(<ApproveBar run={record({ status: "running" })} {...noop} />);

    expect(screen.queryByRole("button", { name: /Submit/ })).toBeNull();
  });

  it("stops pointing at the CLI once a payload is approved", () => {
    /** The bar used to end "run `studio runs submit <id>` when you are ready to
     * spend", which was the whole of the friction this closes. */
    render(<ApproveBar run={record(approved)} {...noop} />);

    expect(screen.queryByText(/studio runs submit/)).toBeNull();
    expect(screen.getByText(/starts billing/)).toBeTruthy();
  });

  it("disables the button while a submission is in flight", () => {
    render(<ApproveBar run={record(approved)} {...noop} busy />);

    expect(
      screen
        .getByRole("button", { name: /Submitting/ })
        .hasAttribute("disabled"),
    ).toBe(true);
  });
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
