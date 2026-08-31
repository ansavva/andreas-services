import { useState } from "react";

import { Alert, Badge, Button, Dialog, Text, buttonClass } from "@ansavva/design-system";

import { Frame, SendRow, Slot } from "../scene/Sends";
import type { RunAsset, RunRecord, RunSend } from "../../types";
import { formatDate, formatTextContent } from "../../utils/format";

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
        <Text variant="title">Plan</Text>
        <Text variant="body" tone="muted">
          This run predates the plan, and its request could not be reconstructed.
        </Text>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Text variant="title">Plan</Text>
        {run.plan?.origin === "backfilled" && (
          // Said plainly rather than hidden. A reconstructed plan is not a
          // person's words about their own intent — it is what the recorded
          // request implies about it — and a reader deciding whether to trust a
          // detail needs to know which they are looking at.
          <Badge intent="neutral">reconstructed</Badge>
        )}
        {run.plan?.params?.aspect_ratio ? (
          <Badge intent="neutral">{String(run.plan.params.aspect_ratio)}</Badge>
        ) : null}
      </div>

      {run.plan?.origin === "backfilled" && (
        <Text variant="caption" tone="muted" className="max-w-prose">
          Rebuilt from the request this run recorded when it was submitted. The prompt and
          the parameters are exactly what went out; the note a person would have written is
          not recoverable, because nothing asked for one at the time.
        </Text>
      )}

      {run.plan?.note && (
        <Text variant="body" className="max-w-prose">
          {run.plan.note}
        </Text>
      )}

      {run.plan?.prompt != null && <Prompt prompt={run.plan.prompt} />}

      {run.plan && Object.keys(run.plan.params).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(run.plan.params).map(([key, value]) => (
            <span key={key} className="rounded-none border border-line bg-card px-2 py-1">
              <Text variant="caption" tone="muted">
                {key}
              </Text>{" "}
              <Text variant="caption">{String(value)}</Text>
            </span>
          ))}
        </div>
      )}

      <Sends sends={run.sends} onView={onView} />
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
function Sends({ sends, onView }: { sends: RunSend[]; onView: (a: RunAsset) => void }) {
  if (sends.length === 0) {
    return (
      <SendRow label="Images">
        <Slot note="none sent" />
      </SendRow>
    );
  }

  const byRole = (role: RunSend["role"]) => sends.filter((send) => send.role === role);
  const start = byRole("start");
  const end = byRole("end");
  const rest = sends.filter((send) => !["start", "end"].includes(send.role ?? ""));

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

function Send({ send, onView }: { send: RunSend; onView: (a: RunAsset) => void }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <Frame hint={String(send.order)} title={send.name} asset={send} onOpen={onView} />
      <Text variant="caption" tone="muted" className="max-w-24 truncate text-center">
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
function Prompt({ prompt }: { prompt: unknown }) {
  const text = typeof prompt === "string" ? prompt : JSON.stringify(prompt, null, 2);
  return (
    // `whitespace-pre-wrap break-words`, not `overflow-auto` alone: a prompt is
    // prose, and at 390px an unwrapped one runs off the right edge and has to be
    // scrolled sideways a line at a time. A structured prompt keeps its
    // indentation, which is what `pre-wrap` preserves and `normal` would not.
    <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-none border border-line bg-card p-3 font-mono text-xs leading-relaxed text-ink">
      <code>{formatTextContent(text, typeof prompt === "string" ? "text" : "json")}</code>
    </pre>
  );
}

/**
 * The approve bar — the one control on this page that leads to money.
 *
 * **It says the digest state in words rather than showing a hash.** What matters
 * to a person is one of three sentences: nobody has approved this, somebody
 * approved exactly this, or somebody approved something that has since changed.
 * The third is the reason the mechanism exists at all — hard rule #2 says
 * re-approve after *any* edit, and until the digest existed nothing checked it.
 */
export function ApproveBar({
  run,
  onApprove,
  onRevoke,
  onSubmit,
  busy,
  error,
}: {
  run: RunRecord;
  onApprove: () => void;
  onRevoke: () => void;
  onSubmit: () => void;
  busy: boolean;
  error: string | null;
}) {
  const [confirming, setConfirming] = useState(false);

  if (run.status !== "draft" && run.status !== "approved") {
    if (!run.approval) return null;
    return (
      <Text variant="caption" tone="muted">
        {run.approval.by === "backfill"
          ? "Approved before approvals were recorded — stamped by the backfill at the moment this run was created."
          : `Approved by ${run.approval.by} on ${formatDate(run.approval.at)}.${
              run.approval.via === "relayed"
                ? " Relayed — the yes was given elsewhere and passed on by an agent, not entered here."
                : ""
            }`}
      </Text>
    );
  }

  return (
    <section className="flex flex-col gap-2 rounded-none border border-line bg-card p-3">
      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>That did not work</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Text variant="body" className="min-w-48 flex-1">
          {sentence(run)}
        </Text>

        {run.status === "approved" && !run.stale ? (
          <>
            <Button intent="ghost" size="sm" onClick={onRevoke} disabled={busy}>
              Revoke
            </Button>
            {/* **The click that spends, and it is deliberately not behind a
                second dialog.** The approve dialog is where a person reads the
                payload and says yes to it; asking again here would be approval
                theatre, and it would teach somebody to click through the one
                prompt that matters. It mirrors the CLI exactly, where `runs
                approve` confirms and `runs submit` simply goes.

                What stands in for a confirm is that this button only exists on
                a run that is approved AND whose payload has not moved since —
                every other state renders the approve control instead. */}
            <Button intent="primary" size="sm" onClick={onSubmit} disabled={busy}>
              {busy ? "Submitting…" : "Submit — this spends"}
            </Button>
          </>
        ) : (
          <Dialog.Root open={confirming} onOpenChange={setConfirming}>
            {/* The trigger IS the button, styled — `Dialog.Trigger` renders its
                own `<button>`, so wrapping a `Button` in one nests a button in a
                button and the browser quietly makes the press do nothing.
                `buttonClass` is what the package exports for this. */}
            <Dialog.Trigger className={buttonClass({ size: "sm" })} disabled={busy}>
              {run.stale ? "Review and approve again" : "Approve this payload"}
            </Dialog.Trigger>
            <Dialog.Backdrop />
            <Dialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
              <Dialog.Title>Approve this payload?</Dialog.Title>
              <Text variant="body">
                You are approving the prompt, the parameters and the {run.sends.length} image
                {run.sends.length === 1 ? "" : "s"} above, in that order. Editing any of them
                afterwards withdraws this approval — nothing can be submitted on a yes given
                to something else.
              </Text>
              <div className="flex flex-wrap justify-end gap-2">
                <Dialog.Close>Cancel</Dialog.Close>
                <Button
                  onClick={() => {
                    setConfirming(false);
                    onApprove();
                  }}
                >
                  Approve
                </Button>
              </div>
            </Dialog.Popup>
          </Dialog.Root>
        )}
      </div>

      <Text variant="caption" tone="muted">
        {run.status === "approved" && !run.stale
          ? "Submitting sends the payload above to the model and starts billing. The run closes itself when the model answers — you can leave this page."
          : "Approving records who and when. It does not send anything; a Submit button appears once this payload is approved."}
      </Text>
    </section>
  );
}

/**
 * A run that went out and has not come back. **The one control for a stuck run.**
 *
 * A generation is closed by the provider calling the API back, which is what
 * lets a person shut this tab — and which introduces a state that did not exist
 * while the CLI held the whole lifecycle: sent, still `running`, and nothing has
 * reported. Usually that is simply a model taking its time, so this says so
 * plainly and offers the check rather than implying something is wrong.
 *
 * **Not shown on a run with no prediction id.** That one never reached the
 * provider, so there is nothing to ask about; the fix is to submit it, and the
 * approve bar above is already where that happens.
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
  if (!run.prediction_id) {
    return (
      <Alert.Root intent="warning">
        <Alert.Title>This run went out and named no prediction</Alert.Title>
        <Alert.Description>
          It was declared before the provider was called and never got an answer, so
          nothing is known to be running. Nothing further will happen on its own.
        </Alert.Description>
      </Alert.Root>
    );
  }

  return (
    <section className="flex flex-col gap-2 rounded-none border border-line bg-card p-3">
      {error && (
        <Alert.Root intent="danger">
          <Alert.Title>That did not work</Alert.Title>
          <Alert.Description>{error}</Alert.Description>
        </Alert.Root>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Text variant="body" className="min-w-48 flex-1">
          Working. This page is watching it and will fill in on its own; closing the tab
          changes nothing.
        </Text>
        <Button intent="ghost" size="sm" onClick={onReconcile} disabled={busy}>
          {busy ? "Checking…" : "Check now"}
        </Button>
      </div>
      <Text variant="caption" tone="muted">
        Only worth pressing if this has sat here far longer than the model usually
        takes — it asks the provider directly, in case the report back was lost.
      </Text>
    </section>
  );
}

function sentence(run: RunRecord): string {
  if (run.stale) {
    return "This payload changed after it was approved. Nothing can be submitted until it is read and approved again.";
  }
  if (run.status === "approved") {
    if (run.approval?.via === "relayed") {
      return `Approved by ${run.approval.by}, relayed — this exact payload is cleared to submit, on a yes given elsewhere and passed on rather than entered here.`;
    }
    return `Approved${run.approval ? ` by ${run.approval.by}` : ""} — this exact payload is cleared to submit.`;
  }
  return "Nothing has been approved. This run cannot be submitted until somebody reads the payload above and says yes to it.";
}
