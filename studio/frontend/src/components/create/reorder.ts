import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
} from "react";

/**
 * Dragging a reference tile along the row to change its position.
 *
 * **Pointer events, not the drag-and-drop API.** `dragRef.ts` uses the latter
 * to carry a picture out of the library and onto the sheet, and that is the
 * right tool for a drop that crosses surfaces — but Safari on iOS starts no
 * HTML drag from a touch, and a phone is where the row most needs
 * reordering, its tiles being what a thumb can reach and the prompt below
 * citing them by number. Pointer events fire the same way for a mouse and
 * a finger, so one gesture serves both.
 *
 * **A finger holds; a mouse just moves.** The row scrolls sideways, and a
 * touch that moves at once is a scroll — so a touch has to rest for
 * `HOLD_MS` before the tile lifts, and a touch that travels first is left
 * to the browser, which cancels the pointer when its scroll begins. Once
 * lifted, `touchmove` is prevented (the listener is registered non-passive
 * for exactly that) so the row holds still under the drag. A mouse has no
 * scroll to protect and lifts after `SLOP` pixels, which is also what
 * separates a drag from a press: a press that never travelled still opens
 * the picker.
 *
 * **The row reorders live.** Crossing the middle of a neighbour swaps places
 * with it — the way a home screen does — rather than drawing a gap and
 * committing on release. That keeps the state simple (the list IS the
 * picture) and makes the caption under each tile true throughout: `Image 2`
 * is whatever is second right now. The lifted tile follows the pointer by
 * a transform; after each swap its untransformed place has moved, so the
 * offset is recomputed from the DOM in a layout effect before the frame is
 * painted, and the tile does not jump.
 *
 * **The row scrolls itself when the drag reaches an edge**, since a tile
 * dragged towards a position that is scrolled out of view cannot otherwise
 * get there. The nudge runs on animation frames while the pointer rests
 * within `EDGE` of either side of the scroller.
 *
 * The keyboard has its own way: arrow keys on a focused tile. A tile is a
 * button, and a button does nothing with arrows otherwise.
 */
const HOLD_MS = 250;
const SLOP = 6;
const EDGE = 28;
const NUDGE = 8;

/** Set on each reorderable tile's wrapper, so a sibling can be found and measured. */
export const POSITION_ATTR = "data-ref-position";
/** Set on the scroller the tiles live in. */
export const ROW_ATTR = "data-attach-row";

interface Gesture {
  pointerId: number;
  el: HTMLElement;
  position: number;
  startX: number;
  startY: number;
  /** Where in the tile the pointer took hold, so the tile does not snap to it. */
  grabX: number;
  lastX: number;
  /** The transform applied right now — subtracted to find the tile's own place. */
  dx: number;
  active: boolean;
  hold: number | null;
  nudge: number | null;
  onTouchMove: (event: TouchEvent) => void;
  onContextMenu: (event: Event) => void;
}

export interface Sortable {
  /** Spread onto the tile's wrapper. */
  wrapper: {
    onPointerDown: (event: PointerEvent<HTMLElement>) => void;
    onPointerMove: (event: PointerEvent<HTMLElement>) => void;
    onPointerUp: (event: PointerEvent<HTMLElement>) => void;
    onPointerCancel: (event: PointerEvent<HTMLElement>) => void;
    onClickCapture: (event: MouseEvent<HTMLElement>) => void;
    style: CSSProperties | undefined;
    [POSITION_ATTR]: number;
    "data-dragging": "" | undefined;
  };
  /** Spread onto the tile's button: the arrow keys. */
  button: { onKeyDown: (event: KeyboardEvent<HTMLElement>) => void };
  dragging: boolean;
}

export function useReorder(
  count: number,
  onMove: (from: number, to: number) => void,
): (position: number) => Sortable {
  const [drag, setDrag] = useState<{ position: number; dx: number } | null>(
    null,
  );
  const gesture = useRef<Gesture | null>(null);
  /** A press that became a drag must not also open the picker on release. */
  const swallowClick = useRef(false);
  // Read through a ref: the nudge's animation frame and the pointer capture
  // outlive the render whose `onMove` they were made in, and the caller's
  // position-to-index mapping changes with every swap.
  const latest = useRef(onMove);
  latest.current = onMove;

  const end = useCallback(() => {
    const g = gesture.current;
    if (!g) return;
    gesture.current = null;
    if (g.hold !== null) window.clearTimeout(g.hold);
    if (g.nudge !== null) window.cancelAnimationFrame(g.nudge);
    g.el.removeEventListener("touchmove", g.onTouchMove);
    g.el.removeEventListener("contextmenu", g.onContextMenu);
    if (g.active) {
      if (g.el.hasPointerCapture?.(g.pointerId))
        g.el.releasePointerCapture(g.pointerId);
      // The click a mouse makes on release comes before the next task; a
      // touch whose moves were prevented makes none, and must not leave the
      // NEXT honest press swallowed.
      swallowClick.current = true;
      window.setTimeout(() => (swallowClick.current = false), 0);
    }
    setDrag(null);
  }, []);

  /** Where the tile is and which neighbour, if any, it has crossed. */
  const track = useCallback((g: Gesture, clientX: number) => {
    g.lastX = clientX;
    const rect = g.el.getBoundingClientRect();
    const ownLeft = rect.left - g.dx;
    g.dx = clientX - g.grabX - ownLeft;
    setDrag({ position: g.position, dx: g.dx });

    const row = g.el.closest<HTMLElement>(`[${ROW_ATTR}]`);
    const siblings = Array.from(
      (row ?? g.el.parentElement)?.querySelectorAll<HTMLElement>(
        `[${POSITION_ATTR}]`,
      ) ?? [],
    ).filter((each) => each !== g.el);
    let target = g.position;
    for (const each of siblings) {
      const at = Number(each.getAttribute(POSITION_ATTR));
      const box = each.getBoundingClientRect();
      const middle = box.left + box.width / 2;
      if (at < g.position && clientX < middle) target = Math.min(target, at);
      if (at > g.position && clientX > middle) target = Math.max(target, at);
    }
    if (target !== g.position) {
      latest.current(g.position, target);
      g.position = target;
    }

    // Near an edge of the scroller: keep nudging it while the pointer rests there.
    if (g.nudge !== null) window.cancelAnimationFrame(g.nudge);
    g.nudge = null;
    if (row) {
      const edge = row.getBoundingClientRect();
      const by =
        clientX < edge.left + EDGE && row.scrollLeft > 0
          ? -NUDGE
          : clientX > edge.right - EDGE &&
              row.scrollLeft < row.scrollWidth - row.clientWidth
            ? NUDGE
            : 0;
      if (by !== 0) {
        g.nudge = window.requestAnimationFrame(() => {
          g.nudge = null;
          if (gesture.current !== g || !g.active) return;
          row.scrollLeft += by;
          track(g, g.lastX);
        });
      }
    }
  }, []);

  const activate = useCallback(
    (g: Gesture) => {
      g.active = true;
      if (g.hold !== null) window.clearTimeout(g.hold);
      g.hold = null;
      g.el.setPointerCapture?.(g.pointerId);
      track(g, g.lastX);
    },
    [track],
  );

  // After a swap the tile's own place has moved: put the transform right
  // before paint, from where the pointer last was. On the position only —
  // a plain move has already set the transform from the same measurement.
  const position = drag?.position;
  useLayoutEffect(() => {
    const g = gesture.current;
    if (!g || !g.active || position === undefined) return;
    const rect = g.el.getBoundingClientRect();
    const ownLeft = rect.left - g.dx;
    const dx = g.lastX - g.grabX - ownLeft;
    if (dx !== g.dx) {
      g.dx = dx;
      setDrag({ position: g.position, dx });
    }
  }, [position]);

  return useCallback(
    (position: number): Sortable => {
      const dragging = drag?.position === position;
      const onPointerDown = (event: PointerEvent<HTMLElement>) => {
        if (gesture.current || count < 2) return;
        if (event.pointerType === "mouse" && event.button !== 0) return;
        const el = event.currentTarget;
        const rect = el.getBoundingClientRect();
        const g: Gesture = {
          pointerId: event.pointerId,
          el,
          position,
          startX: event.clientX,
          startY: event.clientY,
          grabX: event.clientX - rect.left,
          lastX: event.clientX,
          dx: 0,
          active: false,
          hold: null,
          nudge: null,
          // Non-passive on purpose: a passive listener cannot prevent the scroll.
          onTouchMove: (touch) => {
            if (gesture.current === g && g.active) touch.preventDefault();
          },
          // A held touch is a drag here, not a request for the image's menu.
          onContextMenu: (menu) => {
            if (gesture.current === g) menu.preventDefault();
          },
        };
        el.addEventListener("touchmove", g.onTouchMove, { passive: false });
        el.addEventListener("contextmenu", g.onContextMenu);
        gesture.current = g;
        if (event.pointerType !== "mouse") {
          g.hold = window.setTimeout(() => {
            g.hold = null;
            if (gesture.current === g) activate(g);
          }, HOLD_MS);
        }
      };
      const onPointerMove = (event: PointerEvent<HTMLElement>) => {
        const g = gesture.current;
        if (!g || g.pointerId !== event.pointerId) return;
        if (g.active) {
          track(g, event.clientX);
          return;
        }
        const travelled = Math.hypot(
          event.clientX - g.startX,
          event.clientY - g.startY,
        );
        if (event.pointerType === "mouse") {
          g.lastX = event.clientX;
          if (travelled > SLOP) activate(g);
        } else if (travelled > SLOP) {
          // Moved before the hold was up: a scroll, and the browser's.
          end();
        }
      };
      const onPointerUp = (event: PointerEvent<HTMLElement>) => {
        if (gesture.current?.pointerId === event.pointerId) end();
      };
      return {
        wrapper: {
          onPointerDown,
          onPointerMove,
          onPointerUp,
          onPointerCancel: onPointerUp,
          onClickCapture: (event) => {
            if (!swallowClick.current) return;
            swallowClick.current = false;
            event.preventDefault();
            event.stopPropagation();
          },
          style: dragging
            ? { transform: `translateX(${drag!.dx}px)`, touchAction: "none" }
            : undefined,
          [POSITION_ATTR]: position,
          "data-dragging": dragging ? "" : undefined,
        },
        button: {
          onKeyDown: (event) => {
            const to =
              event.key === "ArrowLeft"
                ? position - 1
                : event.key === "ArrowRight"
                  ? position + 1
                  : null;
            if (to === null || to < 0 || to >= count) return;
            event.preventDefault();
            latest.current(position, to);
          },
        },
        dragging,
      };
    },
    [drag, count, activate, track, end],
  );
}
