import { useCallback, useState } from "react";

import {
  Alert,
  Badge,
  Text,
  Tooltip,
  buttonClass,
} from "@ansavva/design-system";

import { Frame, SendRow, Slot } from "../scene/Sends";
import { PromptFields } from "../scene/motionPrompt";
import { ApiError } from "../../apis/client";
import { approveRun, submitRun } from "../../apis/studio";
import type { RunAsset, RunRecord, RunSend } from "../../types";
import { formatDate, formatTextContent } from "../../utils/format";
import { getUserEmail, getUserSub } from "../../auth/oauth";
import { useArmed } from "../../hooks/useArmed";

/**
 * What a run WAS FOR — the half a run page could not show until runs had a plan.
 *
 * Everything below `Outputs` on this page is the result of a submission. This is
 * the intent behind it: the prompt a person wrote, the parameters they chose,
 * and the ordered images the model was handed with a word each about why. Until
 * a run carried a plan all of that lived inside `request.json` — the provider's
 * document, which studio stores and is forbidden to decode — so the app could
 * show what came out of a run and never what it was.
 *
 * **Drawn like a storyboard, using the storyboard's own components.** A shot and
 * a run are the same object at two tiers: both are a plan plus the images it
 * sends, and drawing them differently is what would need justifying. `Frame`,
 * `SendRow` and `Slot` come from `scene/Sends` rather than being copied.
 */
export function RunPlan({
  run,
  onView,
}: {
  run: RunRecord;
  onView: (asset: RunAsset) => void;
}) {
  if (!run.plan && run.sends.length === 0) {
    return (
      <section className="flex flex-col gap-2">
        <Text variant="body" tone="muted">
          This run predates the plan, and its request could not be
          reconstructed.
        </Text>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3">
      {/* No `Plan` heading: the tab above already says it, and two of them a
          few pixels apart read as two sections.

          No lone `aspect_ratio` badge either. It was one parameter promoted out
          of `plan.params` to the top of the section — where it read as a label
          for the whole plan rather than as one setting among several — while
          the same value was drawn again as a chip below with every other
          parameter. `reconstructed` stays: that is a fact about the plan
          itself, not one of its values. */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 empty:hidden">
        {run.plan?.origin === "backfilled" && (
          // Said plainly rather than hidden. A reconstructed plan is not a
          // person's words about their own intent — it is what the recorded
          // request implies about it — and a reader deciding whether to trust a
          // detail needs to know which they are looking at.
          <Badge intent="neutral">reconstructed</Badge>
        )}
      </div>

      {run.plan?.origin === "backfilled" && (
        <Text variant="caption" tone="muted" className="max-w-prose">
          Rebuilt from the request this run recorded when it was submitted. The
          prompt and the parameters are exactly what went out; the note a person
          would have written is not recoverable, because nothing asked for one
          at the time.
        </Text>
      )}

      {run.plan?.note && (
        <Text variant="body" className="max-w-prose">
          {run.plan.note}
        </Text>
      )}

      {/* **Images, then the words.** A shot's plan read this way round and a
          run's read the other, which is two answers to "what am I looking at
          first" for one artifact. The pictures are what a person recognises;
          the document is what they then read. */}
      <Sends sends={run.sends} onView={onView} />

      {run.plan && Object.keys(run.plan.params).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(run.plan.params).map(([key, value]) => (
            <span
              key={key}
              className="rounded-none border border-line bg-card px-2 py-1"
            >
              <Text variant="caption" tone="muted">
                {key}
              </Text>{" "}
              <Text variant="caption">{String(value)}</Text>
            </span>
          ))}
        </div>
      )}

      {/* **Fields, not JSON.** This is studio's own compiled document with a
          schema `studio prompt` validates — not the provider's payload, whose
          shape studio does not own and does not parse. 1.4 kB of escaped JSON
          is not showing anyone their prompt, which is the reason a shot has
          drawn it this way all along. */}
      {run.plan?.prompt != null && (
        <PromptFields
          prompt={
            typeof run.plan.prompt === "string"
              ? run.plan.prompt
              : JSON.stringify(run.plan.prompt)
          }
        />
      )}
    </section>
  );
}

/**
 * The images this run sent, grouped by what each was FOR and kept in order.
 *
 * **Order is not presentational.** A model is handed a list and prompts cite
 * positions in it — a real production prompt in this library reads "the FIRST
 * image is an existing reference of him" — so the number on each tile is part of the
 * payload rather than a label for it.
 */
function Sends({
  sends,
  onView,
}: {
  sends: RunSend[];
  onView: (a: RunAsset) => void;
}) {
  if (sends.length === 0) {
    return (
      <SendRow label="Images">
        <Slot note="none sent" />
      </SendRow>
    );
  }

  const byRole = (role: RunSend["role"]) =>
    sends.filter((send) => send.role === role);
  const start = byRole("start");
  const end = byRole("end");
  const rest = sends.filter(
    (send) => !["start", "end"].includes(send.role ?? ""),
  );

  return (
    <div className="flex flex-col gap-3 rounded-none border border-line p-2">
      {start.length > 0 && (
        <SendRow label="Start frame">
          {start.map((send) => (
            <Send key={send.node} send={send} onView={onView} />
          ))}
        </SendRow>
      )}
      {end.length > 0 && (
        <SendRow label="End frame">
          {end.map((send) => (
            <Send key={send.node} send={send} onView={onView} />
          ))}
        </SendRow>
      )}
      {rest.length > 0 && (
        <SendRow label={start.length || end.length ? "References" : "Images"}>
          {rest.map((send) => (
            <Send key={send.node} send={send} onView={onView} />
          ))}
        </SendRow>
      )}
    </div>
  );
}

function Send({
  send,
  onView,
}: {
  send: RunSend;
  onView: (a: RunAsset) => void;
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <Frame
        hint={String(send.order)}
        title={send.name}
        asset={send}
        onOpen={onView}
      />
      <Text
        variant="caption"
        tone="muted"
        className="max-w-24 truncate text-center"
      >
        {describe(send)}
      </Text>
    </div>
  );
}

/**
 * Where one image came from, in as few words as will still mean something.
 *
 * This is the half `bindings` could never hold. The map said six images went to
 * `image_input`; it could not say that four were a character's face references
 * and two were frames off an earlier run. `catalog.source_of` derives it from
 * where each node sits, so a backfilled run says it the same way.
 */
function describe(send: RunSend): string {
  const source = send.source ?? { kind: "object" };
  switch (source.kind) {
    case "character":
      return source.group ? `character · ${source.group}` : "character";
    case "run":
      return source.output ? `earlier run · #${source.output}` : "earlier run";
    case "input-pool":
      return `input ${source.position ?? "?"}`;
    case "project":
      return "project file";
    default:
      return send.field;
  }
}

/**
 * The prompt, as the document it is.
 *
 * `formatTextContent` re-indents JSON for reading and is the only thing done to
 * it — no field is looked up and nothing branches on the shape. A structured
 * prompt is authored as JSON by `studio prompt`, and flattening one into a
 * paragraph would throw away the structure that makes it re-editable.
 */
/**
 * A prompt document, drawn the one way.
 *
 * Exported because a scene's shot carries the same thing — a compiled prompt
 * document — and was drawing it as a definition list of Subject / Action /
 * Style while the run screen drew it as the document it is. Two renderings of
 * one artifact is how they drift.
 */
export function Prompt({ prompt }: { prompt: unknown }) {
  const text =
    typeof prompt === "string" ? prompt : JSON.stringify(prompt, null, 2);
  return (
    // `whitespace-pre-wrap break-words`, not `overflow-auto` alone: a prompt is
    // prose, and at 390px an unwrapped one runs off the right edge and has to be
    // scrolled sideways a line at a time. A structured prompt keeps its
    // indentation, which is what `pre-wrap` preserves and `normal` would not.
    <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-none border border-line bg-card p-3 font-mono text-xs leading-relaxed text-ink">
      <code>
        {formatTextContent(text, typeof prompt === "string" ? "text" : "json")}
      </code>
    </pre>
  );
}

/**
 * Arm on the first press, act on the second — the confirmation lives in the
 * button, never in a dialog.
 *
 * The mechanics are `useArmed`'s, shared with `ConfirmDeleteButton`: the same
 * three things disarm it — the timeout, focus leaving, and Escape — so a
 * half-pressed control is never still live when you come back to it, and it
 * never swallows an Escape meant for something around it.
 *
 * **Not a prop on that button, because everything else about it is the delete.**
 * Its labels all contain the word, its resting face is a trash can and its armed
 * face is a danger fill; a `tone` prop turning all three off would be a second
 * component wearing the first's name. So the arm/disarm machine is shared and
 * the paint is not.
 *
 * It lives in this file because both callers are the run surface's own money
 * controls — the one-act `RunBar` below, and `RunAgainButton` beside it.
 */
export function ArmedButton({
  idle,
  armed,
  busy,
  tooltip,
  onFire,
  disabled = false,
}: {
  /** At rest. A word or two — what pressing does. */
  idle: string;
  /**
   * Armed. Short, and still says it spends.
   *
   * **This used to be a sentence**, and the surrounding block used to be three
   * more: what a re-run is, what it copies, where the page goes afterwards. A
   * control explained at that length reads as a warning nobody finishes. The
   * explanation moved to the tooltip; what stays on the button is the fact that
   * the next press costs money, which is the half a person needs at the moment
   * they press it.
   */
  armed: string;
  busy: string;
  /** The sentence that used to sit beside the button, on hover and on focus. */
  tooltip: string;
  /** Runs on the second press. Rejecting leaves the button disarmed. */
  onFire: () => Promise<unknown>;
  disabled?: boolean;
}) {
  const state = useArmed({ onFire });
  const label = state.busy ? busy : state.armed ? armed : idle;

  return (
    <Tooltip.Root>
      {/* **The trigger IS the button, styled.** `Tooltip.Trigger` renders a
          `<button>`, and a Button inside it would be a button inside a button —
          invalid, and resolved by browsers dropping one of the two. Same
          composition `Dialog.Trigger` takes elsewhere in this app.

          `primary`, not the delete's danger fill: this spends money and
          destroys nothing, and dressing it in red would say the wrong one. */}
      <Tooltip.Trigger
        className={buttonClass({ intent: "primary", size: "sm" })}
        onClick={state.press}
        {...state.handlers}
        disabled={disabled || state.busy}
      >
        {label}
      </Tooltip.Trigger>
      {/* Anchored to the trigger's right edge rather than centred on it. This
          button sits at the right of its column, and a bubble centred on it
          hangs off the side of the viewport — the text was clipped mid-word. */}
      <Tooltip.Content className="left-auto right-0 translate-x-0">
        {tooltip}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}

/** A stale or refused approval, said in terms of what to do about it. */
function hintFor(code: string | undefined): string | null {
  if (code === "stale_digest")
    return "The plan above has been re-read — check it and run again.";
  if (code === "not_approved")
    return "The approval did not stick; run again to write a fresh one.";
  return null;
}

/** The caller's own address, so an approval by them does not read as a stranger's. */
function named(by: string, me: { sub: string | null; email: string | null }): string {
  return me.sub && by === me.sub ? (me.email ?? "you") : by;
}

/**
 * Running a draft — **one armed press, and that press is the approval.**
 *
 * This used to be an approve `Dialog`, a Revoke button and a separate Submit,
 * with three sentences describing which of the digest's three states the run was
 * in. The separate approve step was redundant in a UI where the payload is on
 * screen: the page renders the plan, the ordered images and — since the payload
 * preview — the exact document a draft would send. Asking for a yes over that
 * and then asking again under a different word is what teaches somebody to click
 * through the first one.
 *
 * **The mechanism is untouched.** `POST /approve` carries the digest this page
 * is rendering and runs immediately before `POST /submit`, so the API's
 * compare-and-swap still refuses a payload that moved underneath — a 409 that
 * reaches the alert below rather than a submission. Every other caller, the CLI
 * included, is unaffected.
 */
export function RunBar({
  run,
  onRan,
  onReload,
}: {
  run: RunRecord;
  onRan: (next: RunRecord) => void;
  /** Re-read after a refusal: the digest the page holds is the stale one. */
  onReload: () => void;
}) {
  const [failure, setFailure] = useState<{ message: string; hint: string | null } | null>(null);

  const fire = useCallback(async () => {
    setFailure(null);
    try {
      // Approve THEN submit, in that order and never merged: a refusal on the
      // first means nothing was sent, which is the distinction the alert draws.
      await approveRun(run.id, run.plan_digest ?? "");
      onRan(await submitRun(run.id));
    } catch (err) {
      const error = err as ApiError;
      setFailure({ message: error.message, hint: hintFor(error.code) });
      onReload();
    }
  }, [onRan, onReload, run.id, run.plan_digest]);

  const me = { sub: getUserSub(), email: getUserEmail() };

  if (run.status !== "draft" && run.status !== "approved") {
    // Sent already. What is left to say is who said yes, and how.
    if (!run.approval) return null;
    return (
      <Text variant="caption" tone="muted">
        {run.approval.by === "backfill"
          ? "Approved before approvals were recorded — stamped by the backfill at the moment this run was created."
          : `Approved by ${named(run.approval.by, me)} on ${formatDate(run.approval.at)}.${
              run.approval.via === "relayed"
                ? " Relayed — the yes was given elsewhere and passed on by an agent, not entered here."
                : ""
            }`}
      </Text>
    );
  }

  return (
    // No frame: a bordered card around one button is chrome for its own sake.
    // The alert brings its own when there is something to say.
    <section className="flex flex-col items-start gap-2">
      {failure && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not submit the run</Alert.Title>
          <Alert.Description>
            {failure.message}
            {failure.hint ? ` ${failure.hint}` : ""}
          </Alert.Description>
        </Alert.Root>
      )}

      {/* **The button and nothing else.** Three sentences used to sit around it
          — what it sends, that one press arms and the second runs, that the run
          closes itself. A control explained at that length reads as a warning
          nobody finishes, and the payload it describes is already on the page.
          What it does is on hover; what it costs is on the armed press. */}
      <ArmedButton
        idle="Run"
        armed="Press again — this spends"
        busy="Running…"
        tooltip={`Sends the prompt, the parameters and the ${run.sends.length} image${
          run.sends.length === 1 ? "" : "s"
        } above, in that order. Records your approval and starts billing.`}
        onFire={fire}
      />
    </section>
  );
}

/**
 * A run that has gone, and what can be done about one — which is almost nothing.
 *
 * It closes itself: the provider calls the API back, so this page polls until
 * the status can no longer move. `Check now` is for the run that has sat far
 * longer than the model takes, and asks the provider directly in case the
 * report back was lost.
 */
export function InFlightBar({
  run,
  onReconcile,
  busy,
  error,
}: {
  run: RunRecord;
  onReconcile: () => void;
  busy: boolean;
  error: string | null;
}) {
  if (run.status !== "pending" && run.status !== "running") return null;

  // Nothing reached the provider, so there is nothing to ask about.
  if (!run.prediction_id) {
    return (
      <Alert.Root intent="warning">
        <Alert.Title>This run went out and named no prediction</Alert.Title>
        <Alert.Description>
          It was declared before the provider was called and never got an answer, so nothing is
          known to be running. Nothing further will happen on its own.
        </Alert.Description>
      </Alert.Root>
    );
  }

  return (
    <section className="flex flex-col gap-2 rounded-none border border-line bg-card p-3">
      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not check the run</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Text variant="body" className="min-w-48 flex-1">
          Working. This page is watching it and will fill in on its own; closing the tab changes
          nothing.
        </Text>
        <Tooltip.Root>
          <Tooltip.Trigger
            className={buttonClass({ intent: "secondary", size: "sm" })}
            onClick={onReconcile}
            disabled={busy}
          >
            {busy ? "Checking…" : "Check now"}
          </Tooltip.Trigger>
          <Tooltip.Content>
            Asks the provider directly, in case the report back was lost. Only worth pressing if
            this has sat here far longer than the model usually takes.
          </Tooltip.Content>
        </Tooltip.Root>
      </div>
    </section>
  );
}
