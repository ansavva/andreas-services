import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
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
 * **The gesture lives on a grip, not on the tile.** The tile is a press (it
 * opens the preview) sitting in a row that scrolls sideways, and a drag on
 * the same square had to be told apart from both: a touch rested for 250ms
 * before the tile lifted, a mouse travelled a few pixels first. That hold
 * was the thing a thumb got wrong — a touch that moved a little during it
 * was a scroll, one that rested a little long was iOS asking about the
 * image. So the strip at the tile's foot — the caption, `Image 2`, the
 * very thing the drag changes — is the handle: `touch-action: none` on it,
 * so a touch there is ours from the first pixel and never the browser's
 * scroll, and the tile lifts on the press. The picture above it stays a
 * plain press, and a mouse on the picture can never lift the tile by
 * accident. The row still scrolls under a finger on a picture.
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
const EDGE = 28;
const NUDGE = 8;

/** Set on each reorderable tile's wrapper, so a sibling can be found and measured. */
export const POSITION_ATTR = "data-ref-position";
/** Set on the scroller the tiles live in. */
export const ROW_ATTR = "data-attach-row";
/** Set on the grip, so a test can take hold of it. */
export const GRIP_ATTR = "data-ref-grip";

interface Gesture {
  pointerId: number;
  /** The tile: measured, and moved by the transform. */
  el: HTMLElement;
  /** The strip that was pressed: holds the pointer capture. */
  grip: HTMLElement;
  position: number;
  /** Where in the tile the pointer took hold, so the tile does not snap to it. */
  grabX: number;
  lastX: number;
  /** The transform applied right now — subtracted to find the tile's own place. */
  dx: number;
  nudge: number | null;
  onContextMenu: (event: Event) => void;
}

export interface Sortable {
  /** Spread onto the tile's wrapper: where it is, and that it is lifted. */
  wrapper: {
    style: CSSProperties | undefined;
    [POSITION_ATTR]: number;
    "data-dragging": "" | undefined;
  };
  /** Spread onto the grip: the drag. */
  grip: {
    onPointerDown: (event: PointerEvent<HTMLElement>) => void;
    onPointerMove: (event: PointerEvent<HTMLElement>) => void;
    onPointerUp: (event: PointerEvent<HTMLElement>) => void;
    onPointerCancel: (event: PointerEvent<HTMLElement>) => void;
    [GRIP_ATTR]: "";
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
  // Read through a ref: the nudge's animation frame and the pointer capture
  // outlive the render whose `onMove` they were made in, and the caller's
  // position-to-index mapping changes with every swap.
  const latest = useRef(onMove);
  latest.current = onMove;

  const end = useCallback(() => {
    const g = gesture.current;
    if (!g) return;
    gesture.current = null;
    if (g.nudge !== null) window.cancelAnimationFrame(g.nudge);
    g.grip.removeEventListener("contextmenu", g.onContextMenu);
    if (g.grip.hasPointerCapture?.(g.pointerId))
      g.grip.releasePointerCapture(g.pointerId);
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
          if (gesture.current !== g) return;
          row.scrollLeft += by;
          track(g, g.lastX);
        });
      }
    }
  }, []);

  // After a swap the tile's own place has moved: put the transform right
  // before paint, from where the pointer last was. On the position only —
  // a plain move has already set the transform from the same measurement.
  const position = drag?.position;
  useLayoutEffect(() => {
    const g = gesture.current;
    if (!g || position === undefined) return;
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
        const grip = event.currentTarget;
        const el = grip.closest<HTMLElement>(`[${POSITION_ATTR}]`);
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const g: Gesture = {
          pointerId: event.pointerId,
          el,
          grip,
          position,
          grabX: event.clientX - rect.left,
          lastX: event.clientX,
          dx: 0,
          nudge: null,
          // A held touch on the strip is a drag, not a request for a menu.
          onContextMenu: (menu) => {
            if (gesture.current === g) menu.preventDefault();
          },
        };
        grip.addEventListener("contextmenu", g.onContextMenu);
        gesture.current = g;
        grip.setPointerCapture?.(event.pointerId);
        track(g, event.clientX);
      };
      const onPointerMove = (event: PointerEvent<HTMLElement>) => {
        const g = gesture.current;
        if (!g || g.pointerId !== event.pointerId) return;
        track(g, event.clientX);
      };
      const onPointerUp = (event: PointerEvent<HTMLElement>) => {
        if (gesture.current?.pointerId === event.pointerId) end();
      };
      return {
        wrapper: {
          style: dragging
            ? { transform: `translateX(${drag!.dx}px)` }
            : undefined,
          [POSITION_ATTR]: position,
          "data-dragging": dragging ? "" : undefined,
        },
        grip: {
          onPointerDown,
          onPointerMove,
          onPointerUp,
          onPointerCancel: onPointerUp,
          [GRIP_ATTR]: "",
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
    [drag, count, track, end],
  );
}
