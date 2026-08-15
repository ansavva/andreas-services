import { useRef, type PointerEvent as ReactPointerEvent } from "react";

const SWIPE_THRESHOLD_PX = 48;

/**
 * Horizontal swipe on the lightbox, via pointer events so one handler covers
 * touch, pen and a click-drag with a mouse.
 *
 * Only fires when the horizontal travel clearly dominates: a mostly-vertical
 * drag is the user scrolling, and a viewer that jumped to the next photo on
 * that would be infuriating.
 */
export function useSwipe(onPrev: () => void, onNext: () => void) {
  const start = useRef<{ x: number; y: number } | null>(null);

  return {
    onPointerDown(event: ReactPointerEvent) {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      start.current = { x: event.clientX, y: event.clientY };
    },
    onPointerUp(event: ReactPointerEvent) {
      const origin = start.current;
      start.current = null;
      if (!origin) return;

      const dx = event.clientX - origin.x;
      const dy = event.clientY - origin.y;
      if (Math.abs(dx) < SWIPE_THRESHOLD_PX || Math.abs(dx) <= Math.abs(dy)) return;

      if (dx > 0) onPrev();
      else onNext();
    },
    onPointerCancel() {
      start.current = null;
    },
  };
}
