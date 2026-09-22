import { useCallback, useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";

/** A second tap this soon after the first is a double tap. */
export const DOUBLE_TAP_MS = 300;
/** A pointer that travelled further than this was a swipe, not a tap. */
const TAP_SLOP_PX = 12;

interface Point {
  x: number;
  y: number;
}

interface Handlers {
  /** One tap, reported only once a second one has had its chance not to come. */
  onTap?: (at: Point) => void;
  onDoubleTap?: (at: Point) => void;
}

/**
 * A tap and a double tap, told apart from a swipe, for a pane in the reel.
 *
 * **Pointer events, not `click` and `dblclick`.** On a phone `dblclick` is
 * the browser's zoom gesture and does not reach the page reliably, and a
 * `click` fires after a scroll-snap swipe too — the pane under the finger is
 * the pane that was tapped, as far as the browser is concerned.
 *
 * **Travel is summed from `pointermove`, and the up only confirms.** On
 * iOS a touch `pointerup` carries `clientX/Y` of `0,0`, so a down-to-up
 * distance reads every tap as a swipe across the screen (#754). The point
 * reported is where the finger went *down*, for the same reason — it is the
 * only coordinate the phone gives that is real.
 *
 * **A single tap waits `DOUBLE_TAP_MS`.** The first tap of a double tap
 * would otherwise pause the clip the second tap is hearting, and the two
 * cannot be told apart any sooner. The wait is the price of one gesture
 * meaning two things, and it is the wait every reel people already know
 * pays.
 */
export function useTaps({ onTap, onDoubleTap }: Handlers) {
  const down = useRef<{ id: number; at: Point; last: Point; travel: number } | null>(null);
  const lastTap = useRef<{ time: number; at: Point } | null>(null);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Read through a ref so a caller's inline arrows neither re-create the
  // handlers below nor go stale inside the single-tap timer.
  const latest = useRef({ onTap, onDoubleTap });
  useEffect(() => {
    latest.current = { onTap, onDoubleTap };
  });

  useEffect(
    () => () => {
      if (pending.current) clearTimeout(pending.current);
    },
    [],
  );

  const onPointerDown = useCallback((event: ReactPointerEvent) => {
    if (!event.isPrimary) return;
    const at = { x: event.clientX, y: event.clientY };
    down.current = { id: event.pointerId, at, last: at, travel: 0 };
  }, []);

  const onPointerMove = useCallback((event: ReactPointerEvent) => {
    const held = down.current;
    if (!held || held.id !== event.pointerId) return;
    // Summed between moves rather than read off `movementX/Y`, which jsdom
    // and some WebKits leave at 0.
    held.travel += Math.abs(event.clientX - held.last.x) + Math.abs(event.clientY - held.last.y);
    held.last = { x: event.clientX, y: event.clientY };
  }, []);

  const onPointerCancel = useCallback((event: ReactPointerEvent) => {
    if (down.current?.id === event.pointerId) down.current = null;
  }, []);

  const onPointerUp = useCallback((event: ReactPointerEvent) => {
    const held = down.current;
    if (!held || held.id !== event.pointerId) return;
    down.current = null;
    if (held.travel > TAP_SLOP_PX) return;

    // `Date.now()` over `event.timeStamp`: the latter's clock is the
    // browser's, and no fake timer moves it.
    const now = Date.now();
    const previous = lastTap.current;
    if (previous && now - previous.time <= DOUBLE_TAP_MS) {
      lastTap.current = null;
      if (pending.current) {
        clearTimeout(pending.current);
        pending.current = null;
      }
      latest.current.onDoubleTap?.(previous.at);
      return;
    }

    lastTap.current = { time: now, at: held.at };
    pending.current = setTimeout(() => {
      pending.current = null;
      lastTap.current = null;
      latest.current.onTap?.(held.at);
    }, DOUBLE_TAP_MS);
  }, []);

  return { onPointerDown, onPointerMove, onPointerUp, onPointerCancel };
}
