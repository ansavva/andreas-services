import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

/**
 * How long the chrome stays up after the last thing that asked for it.
 *
 * Three seconds is what the big players settle on: long enough to read the
 * time and reach a button, short enough that a clip being judged is a clip
 * rather than a clip under a bar.
 */
export const CHROME_IDLE_MS = 3000;

/**
 * A finger on the picture is either a scroll going past or the tap the
 * click handler answers; neither is a reason to show the chrome. A finger
 * on anything else — a button, the seek bar — is using the chrome, and a
 * drag along the bar must not have the bar vanish under it.
 */
function touchOnPicture(event: ReactPointerEvent<HTMLElement>) {
  return event.pointerType === "touch" && event.target instanceof HTMLMediaElement;
}

/** How far a finger may travel between down and up and still be a tap. */
const TAP_SLOP_PX = 12;

export interface ChromeIdle {
  /** Whether the chrome is drawn. Always true while `active` is false. */
  visible: boolean;
  /** Spread onto the player's box. */
  handlers: {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerLeave: (event: ReactPointerEvent<HTMLElement>) => void;
    onFocus: () => void;
    onKeyDown: () => void;
  };
}

/**
 * Hide the player's chrome while a clip plays and nobody is touching it.
 *
 * **Two input models, told apart by the pointer that arrives, not by the
 * device.** A mouse reveals the chrome by moving and hides it by leaving — the
 * bar is under the cursor whenever the cursor is over the picture, which is
 * how every desktop player behaves. A finger has no hover, so on touch the
 * picture itself is the switch: one tap shows, the next hides, and the timer
 * puts it away again if nothing is pressed. `pointerType` on each event is
 * what says which one is in play, so a laptop with a touchscreen gets both,
 * per gesture.
 *
 * **The tap is read off `pointerup`, not `click`.** iOS Safari does not
 * synthesise `click` for a tap on an element that is not itself clickable —
 * a `<video>` with no `controls` and no listener of its own (React's is on
 * the root) — so a hidden chrome on an iPhone had no way back and no way out
 * of fullscreen. Pointer events fire regardless; down and up within
 * `TAP_SLOP_PX` is a tap, further is a scroll going past.
 *
 * **Paused is not idle.** `active` is the caller's "the clip is running";
 * while it is false the chrome stays up and the timer is off, so pausing a
 * clip to look at a frame keeps the transport exactly where the hand left it.
 *
 * Focus and a key reveal too: a person tabbing to the mute button must be
 * able to see the button they are on, and Space to pause should show what
 * it did.
 */
export function useChromeIdle(active: boolean): ChromeIdle {
  const [hidden, setHidden] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(active);
  /** Where a finger landed on the picture, until it lifts or moves too far. */
  const tap = useRef<{ x: number; y: number } | null>(null);
  activeRef.current = active;

  const clear = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const arm = useCallback(() => {
    clear();
    if (!activeRef.current) return;
    timer.current = setTimeout(() => {
      timer.current = null;
      setHidden(true);
    }, CHROME_IDLE_MS);
  }, [clear]);

  const reveal = useCallback(() => {
    setHidden(false);
    arm();
  }, [arm]);

  // Play starts the clock; anything that stops the clip brings the chrome
  // back and stops it.
  useEffect(() => {
    setHidden(false);
    if (active) arm();
    return clear;
  }, [active, arm, clear]);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (touchOnPicture(event)) {
        tap.current = { x: event.clientX, y: event.clientY };
        return;
      }
      tap.current = null;
      reveal();
    },
    [reveal],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (touchOnPicture(event)) {
        const start = tap.current;
        if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > TAP_SLOP_PX) {
          tap.current = null;
        }
        return;
      }
      reveal();
    },
    [reveal],
  );

  const onPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const start = tap.current;
      tap.current = null;
      if (!start || !touchOnPicture(event) || !activeRef.current) return;
      if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > TAP_SLOP_PX) return;
      if (hidden) {
        reveal();
      } else {
        clear();
        setHidden(true);
      }
    },
    [clear, hidden, reveal],
  );

  const onPointerLeave = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (event.pointerType === "touch" || !activeRef.current) return;
      clear();
      setHidden(true);
    },
    [clear],
  );

  return {
    visible: !active || !hidden,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerLeave,
      onFocus: reveal,
      onKeyDown: reveal,
    },
  };
}
