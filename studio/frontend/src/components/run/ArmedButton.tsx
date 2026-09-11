import type { ReactNode } from "react";

import { Tooltip, buttonClass } from "@ansavva/design-system";

import { useArmed } from "../../hooks/useArmed";

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
 * **Its own file now.** It lived in `RunPlan.tsx` beside `RunBar`, the draft's
 * one-act Run; the feed replaced that page and the run bar with it, and what
 * survives is the money gesture itself — `Rerun` in a feed row, in a rail's
 * action grid, and `Run again` wherever a finished run is drawn whole.
 */
export function ArmedButton({
  idle,
  armed,
  busy,
  tooltip,
  onFire,
  disabled = false,
  intent = "primary",
  icon,
  className = "",
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
  /**
   * `primary` where the button stands alone — it spends money and destroys
   * nothing, so it is never the delete's danger fill. `secondary` in a row of
   * quiet actions, where a filled button would be the loudest thing on the
   * screen; the armed label is what says it spends there.
   */
  intent?: "primary" | "secondary";
  /** Drawn before the word, for the icon+word rows the feed and the rail use. */
  icon?: ReactNode;
  className?: string;
}) {
  const state = useArmed({ onFire });
  const label = state.busy ? busy : state.armed ? armed : idle;

  return (
    <Tooltip.Root>
      {/* **The trigger IS the button, styled.** `Tooltip.Trigger` renders a
          `<button>`, and a Button inside it would be a button inside a button —
          invalid, and resolved by browsers dropping one of the two. Same
          composition `Dialog.Trigger` takes elsewhere in this app. */}
      <Tooltip.Trigger
        className={buttonClass({ intent, size: "sm", className })}
        onClick={state.press}
        {...state.handlers}
        disabled={disabled || state.busy}
      >
        {icon}
        {label}
      </Tooltip.Trigger>
      {/* Anchored to the trigger's right edge rather than centred on it. This
          button often sits at the right of its column, and a bubble centred on
          it hangs off the side of the viewport — the text was clipped mid-word. */}
      <Tooltip.Content className="left-auto right-0 translate-x-0">
        {tooltip}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}
