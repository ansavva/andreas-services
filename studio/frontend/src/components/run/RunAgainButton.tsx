import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Tooltip, buttonClass } from "@ansavva/design-system";

import { approveRun, createRun, submitRun } from "../../apis/studio";
import { ArmedButton } from "./RunPlan";
import { rerunBodyOf } from "./rerun";
import type { RunRecord } from "../../types";
import { runPath } from "../../utils/location";

/**
 * Run this again — a fresh attempt at the same payload, without leaving the page.
 *
 * **A run cannot be re-submitted, and that is not a gap being worked around.** A
 * run row records one submission: its request, its response, its outputs and the
 * approval the payload was sent under. Sending it twice would overwrite the
 * record of the first, so what "again" means is a second run, and the app makes
 * one the way the CLI does — a new draft carrying the same plan and the same
 * ordered images, byte for byte (see `rerunBodyOf`).
 *
 * **One gesture, and the page reseats onto the new attempt.** Create, approve,
 * submit, then swap the address to the new run id — a client-side push into the
 * same page component, so the outputs empty, the in-flight bar appears and the
 * polling resumes without a load. The previous attempt is untouched and browser
 * Back returns to it.
 *
 * The arm-then-fire press IS the approval, exactly as it is in `RunBar`: the
 * payload being approved is the one this page is rendering above the button, and
 * the run created from it is byte-identical to it. Hard rule #2 is about a person
 * reading a payload and saying yes to it, which is what a second press on a
 * button that has just told you it spends is.
 */
export function RunAgainButton({ run }: { run: RunRecord }) {
  const navigate = useNavigate();
  const [failure, setFailure] = useState<string | null>(null);

  /**
   * **Navigates on a partial failure too, and that is the safe direction.**
   *
   * Create is the only step whose failure leaves nothing behind — there is no
   * new run, so this stays put and says why. Once the draft exists it is the
   * thing to look at whatever happened next: approve or submit failing lands a
   * person on a normal unsubmitted run, in front of `RunBar`, which is the
   * recovery path for exactly this and states the refusal in its own words when
   * they press it. Nothing has been billed unless submit returned.
   */
  /**
   * **Clone into a draft, and stop there.** Nothing is approved and nothing is
   * sent, so this spends nothing.
   *
   * The gap this closes: `Run again` re-sends a payload byte-identical to this
   * one, which is the right thing when the run was right and you want another
   * take. It is no use at all when the run was ALMOST right — the reason to
   * look at a finished run and reach for its plan is usually to change a word
   * in it. Editing this run is refused by the API once it has been submitted,
   * and correctly: its plan has to keep describing what was actually sent. So
   * the way to edit a finished run is to make a new one from it.
   */
  const duplicate = useCallback(async () => {
    setFailure(null);
    try {
      const created = await createRun(rerunBodyOf(run));
      // Straight into the editor: a draft cloned to be changed is one nobody
      // wants to land on read-only and then press a second button to open.
      navigate(runPath(run.project, created.id), { state: { editing: true } });
    } catch (err) {
      setFailure((err as Error).message);
    }
  }, [navigate, run]);

  const fire = useCallback(async () => {
    setFailure(null);
    let created;
    try {
      created = await createRun(rerunBodyOf(run));
    } catch (err) {
      setFailure((err as Error).message);
      return;
    }

    try {
      await approveRun(created.id, created.plan_digest);
      await submitRun(created.id);
    } catch {
      /* the new run's own bar is the recovery — see above */
    }
    navigate(runPath(run.project, created.id));
  }, [navigate, run]);

  return (
    // No frame: a bordered card around one button is chrome for its own sake.
    // The alert brings its own when there is something to say.
    <section className="flex flex-col items-end gap-2">
      {failure && (
        <Alert.Root intent="danger">
          <Alert.Title>Nothing was created</Alert.Title>
          <Alert.Description>{failure}</Alert.Description>
        </Alert.Root>
      )}

      {/* **The button alone.** Two paragraphs used to frame it — what a re-run
          copies, and where the page goes afterwards. Both are on hover now: the
          payload they described is already on the page, and a control that
          explains itself at that length is one nobody reads to the end of. */}
      {/* Two things a finished run can still do, and only one of them spends.
          The cheap one is on the left, in the outline weight, so the filled
          button is the one that costs money — the same reading order every
          other action row on this page has. */}
      <div className="flex flex-wrap items-center gap-2">
        <Tooltip.Root>
          <Tooltip.Trigger
            className={buttonClass({ intent: "secondary", size: "sm" })}
            onClick={() => void duplicate()}
          >
            Duplicate
          </Tooltip.Trigger>
          <Tooltip.Content className="left-auto right-0 translate-x-0">
            Copies this run into a new draft and opens it for editing. Nothing
            is sent and nothing is billed until you run it.
          </Tooltip.Content>
        </Tooltip.Root>

        <ArmedButton
          idle="Run again"
          armed="Press again — this spends"
          busy="Running…"
          tooltip="Runs the same prompt, parameters and images as a new attempt. This one keeps its outputs, and the page moves to the new run."
          onFire={fire}
        />
      </div>
    </section>
  );
}
