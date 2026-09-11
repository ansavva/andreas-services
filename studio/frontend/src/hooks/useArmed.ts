import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

/** How long an armed control stays live. Long enough to read, short enough to expire. */
export const ARMED_MS = 4000;

export type ArmedPhase = "idle" | "armed" | "busy";

interface Options {
  /** Runs on `fire`. Rejecting returns the control to rest; the rejection goes to `onError`. */
  onFire: () => Promise<unknown>;
  /**
   * Where a rejection goes. Absent, it is dropped — most callers' pages already
   * report the failure, and a second copy of the message would be noise.
   */
  onError?: (error: unknown) => void;
}

/**
 * Arm on the first press, act on the second — the confirmation is the control
 * changing under your finger, never a dialog.
 *
 * **This is one machine, not three.** `ConfirmDeleteButton`, the delete item in
 * `ItemActions` and the run surface's `ArmedButton` each carried their own copy
 * of it, and the copies had drifted: the menu item had no timeout, so a
 * half-pressed delete could sit live behind a closed menu indefinitely. The
 * shape is shared here and the paint stays with each caller — what a delete
 * looks like and what a spend looks like are different questions from when a
 * second press counts.
 *
 * Three things disarm it: the timeout, focus leaving, and Escape. `handlers`
 * carries the last two, to spread onto whatever element is the control. Escape
 * is intercepted only while armed, so the overlay around the control keeps its
 * own Escape the rest of the time.
 */
export function useArmed({ onFire, onError }: Options) {
  const [phase, setPhase] = useState<ArmedPhase>("idle");
  // Mirrors `phase` synchronously, so two presses in one tick cannot both read
  // "idle" and arm twice, or both read "armed" and fire twice.
  const current = useRef<ArmedPhase>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Set on unmount so a resolving promise cannot call setState afterwards —
  // deleting from the reel closes the pane the button lives in, and a run-again
  // navigates away as its last step.
  const gone = useRef(false);
  const fireRef = useRef(onFire);
  const errorRef = useRef(onError);
  fireRef.current = onFire;
  errorRef.current = onError;

  const move = useCallback((next: ArmedPhase) => {
    current.current = next;
    if (!gone.current) setPhase(next);
  }, []);

  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => {
    gone.current = false;
    return () => {
      gone.current = true;
      clear();
    };
  }, [clear]);

  const disarm = useCallback(() => {
    clear();
    if (current.current === "armed") move("idle");
  }, [clear, move]);

  const arm = useCallback(() => {
    if (current.current === "busy") return;
    clear();
    move("armed");
    timer.current = setTimeout(() => {
      timer.current = null;
      if (current.current === "armed") move("idle");
    }, ARMED_MS);
  }, [clear, move]);

  const fire = useCallback(() => {
    if (current.current === "busy") return;
    clear();
    move("busy");
    void fireRef
      .current()
      .catch((error: unknown) => errorRef.current?.(error))
      .finally(() => move("idle"));
  }, [clear, move]);

  /** The press: arms at rest, fires once armed, ignored while busy. */
  const press = useCallback(() => {
    if (current.current === "armed") fire();
    else arm();
  }, [arm, fire]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape" && current.current === "armed") {
        event.stopPropagation();
        disarm();
      }
    },
    [disarm],
  );

  return {
    phase,
    armed: phase === "armed",
    busy: phase === "busy",
    arm,
    disarm,
    fire,
    press,
    handlers: { onBlur: disarm, onKeyDown },
  };
}
