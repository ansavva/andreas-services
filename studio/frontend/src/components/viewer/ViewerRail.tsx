import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

/**
 * The rail beside a viewer's stage — the opened run's and the open file's.
 *
 * **Resizable from `md`, by the edge it shares with the stage.** The handle
 * is a hairline strip down the rail's left edge; dragging it moves the
 * boundary, the arrow keys nudge it, a double-click puts it back. Below `md`
 * the rail is the full width of a column that scrolls, and the handle is
 * not drawn — there is no boundary to move.
 *
 * **One width for both viewers, remembered.** A person who widened the rail
 * to read a prompt in the opened run expects the same room on the file the
 * run made; the two are the same rail in two places, so they share one key.
 * The write is wrapped for the same reason `SidebarContext`'s is — private
 * Safari throws on the accessor, and forgetting the width is the lesser
 * failure.
 *
 * **Applied through a custom property rather than a `width` style**, so the
 * phone layout's `w-full` is not overridden by an inline style that would
 * win over any class: the number only reaches the box through `md:w-(…)`.
 */

export const RAIL_WIDTH_STORAGE_KEY = "studio.viewer.rail-width";
export const RAIL_WIDTH_DEFAULT = 360;
export const RAIL_WIDTH_MIN = 280;
export const RAIL_WIDTH_MAX = 800;
/** Room the stage keeps whatever the rail takes; the drag stops there. */
const STAGE_MIN = 320;
const KEY_STEP = 16;

function clamp(width: number, viewport = Number.POSITIVE_INFINITY): number {
  const max = Math.min(RAIL_WIDTH_MAX, Math.max(RAIL_WIDTH_MIN, viewport - STAGE_MIN));
  return Math.round(Math.min(max, Math.max(RAIL_WIDTH_MIN, width)));
}

function read(): number {
  try {
    const raw = window.localStorage.getItem(RAIL_WIDTH_STORAGE_KEY);
    const n = raw === null ? Number.NaN : Number(raw);
    return Number.isFinite(n) ? clamp(n) : RAIL_WIDTH_DEFAULT;
  } catch {
    return RAIL_WIDTH_DEFAULT;
  }
}

function write(width: number): void {
  try {
    if (width === RAIL_WIDTH_DEFAULT) window.localStorage.removeItem(RAIL_WIDTH_STORAGE_KEY);
    else window.localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(width));
  } catch {
    /* see `read` */
  }
}

type Props = HTMLAttributes<HTMLElement> & {
  "aria-label": string;
};

export function ViewerRail({ className = "", style, children, ...rest }: Props) {
  const [width, setWidth] = useState<number>(read);
  const [dragging, setDragging] = useState(false);
  const rail = useRef<HTMLElement>(null);
  // The rail's right edge at pointer-down: the width is the distance from the
  // pointer to it, so the boundary tracks the pointer rather than the delta.
  const right = useRef(0);

  const commit = useCallback((next: number) => {
    const w = clamp(next, window.innerWidth);
    setWidth(w);
    write(w);
  }, []);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    right.current = rail.current?.getBoundingClientRect().right ?? e.clientX + width;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
    // No `preventDefault` here: on a pointerdown it also cancels the mouse
    // events the browser derives from it, and the double-click that resets
    // the width is one of them. `select-none` below and the body's
    // `user-select` during the drag are what keep text from selecting.
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    commit(right.current - e.clientX);
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    setDragging(false);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    // The handle sits on the rail's LEFT edge: left grows the rail.
    if (e.key === "ArrowLeft") commit(width + KEY_STEP);
    else if (e.key === "ArrowRight") commit(width - KEY_STEP);
    else if (e.key === "Home") commit(RAIL_WIDTH_MAX);
    else if (e.key === "End") commit(RAIL_WIDTH_MIN);
    else return;
    e.preventDefault();
  };

  // While the pointer is down the whole document takes the resize cursor and
  // gives up text selection: the stage's player would otherwise swap in its
  // own cursor as the pointer crossed it, and a fast drag would select the
  // rail's text.
  useEffect(() => {
    if (!dragging) return;
    const { cursor, userSelect } = document.body.style;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.cursor = cursor;
      document.body.style.userSelect = userSelect;
    };
  }, [dragging]);

  return (
    <>
      {/*
        The handle is the rail's SIBLING, not its child. The rail scrolls
        (`overflow-y-auto`), and a scrolling box clips on both axes, so a
        strip hung off its left edge lost the half that lay outside the
        border — a four-pixel target that missed one drag in two. A
        zero-width flex item between stage and rail is clipped by nothing;
        the strip straddles it, and the frame's row stretches it to the
        full height.
      */}
      <div className="relative hidden w-0 shrink-0 md:block">
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panel"
          aria-valuenow={width}
          aria-valuemin={RAIL_WIDTH_MIN}
          aria-valuemax={RAIL_WIDTH_MAX}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onDoubleClick={() => commit(RAIL_WIDTH_DEFAULT)}
          onKeyDown={onKeyDown}
          // Eight pixels wide, straddling the border, so the target is wider
          // than the hairline it moves; the tint says it is there on hover
          // and while held. `touch-none` keeps a tablet's drag from
          // scrolling instead.
          className={`absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none select-none transition-colors hover:bg-primary/40 focus-visible:bg-primary/60 focus-visible:outline-none ${
            dragging ? "bg-primary/60" : ""
          }`}
        />
      </div>
      <aside
        {...rest}
        ref={rail}
        className={`flex w-full shrink-0 flex-col border-t border-line bg-bg p-5 md:w-(--rail-w) md:overflow-y-auto md:border-l md:border-t-0 ${className}`}
        style={{ "--rail-w": `${width}px`, ...style } as CSSProperties}
      >
        {children}
      </aside>
    </>
  );
}
