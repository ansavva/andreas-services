import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

/**
 * Where a picture is on its stage: how far in, and how far the picture has
 * been pushed from the middle, in stage pixels.
 *
 * `scale` 1 is the fit — the whole picture inside the box, which is what the
 * player draws before anything is touched. The offset is always `0,0` at fit,
 * so `FIT` is the one value every "back to normal" ends at.
 */
export interface ZoomState {
  scale: number;
  x: number;
  y: number;
}

export const FIT: ZoomState = { scale: 1, x: 0, y: 0 };

/** Never further out than the fit; eight times in is past any pixel's worth. */
const MIN = 1;
const MAX = 8;
/** One press of a button, or one `+`/`-` key. */
const STEP = 1.5;
/** A double-click goes here from the fit, and back to the fit from anywhere. */
const DOUBLE = 2.5;
/** How much wheel it takes: a full notch of a mouse wheel is about ×1.2. */
const WHEEL = 0.002;

interface Options {
  /** The box the picture sits in. Gestures are measured against it. */
  container: RefObject<HTMLElement | null>;
  /**
   * The `<img>` itself, for its natural size. The pan is clamped so the
   * picture's edge never leaves the box's edge behind, and that needs the
   * size the picture is drawn at — which `object-contain` decides from the
   * natural size and the box.
   */
  media: RefObject<HTMLImageElement | null>;
  /** Off for a video, and off for a player nobody asked to zoom. */
  enabled: boolean;
  /**
   * Controlled, for two stages that zoom together. The compare stage holds one
   * state and hands it to both players; either one's gesture goes through
   * `onChange` and both redraw. Uncontrolled when absent.
   */
  value?: ZoomState;
  onChange?: (next: ZoomState) => void;
  /**
   * Reset to the fit when this changes — the node, so stepping to another
   * picture in a player that stays mounted starts it at the fit.
   */
  resetKey?: string;
}

/**
 * Zoom and pan for a still, on whatever box the player already draws.
 *
 * **Every gesture the platform has for "closer", and one rule for each.**
 * A pinch — two fingers, or a trackpad's, which arrives as a wheel with
 * `ctrlKey` — zooms about the fingers. A mouse wheel zooms about the pointer
 * wherever the viewer does not scroll — from `md`, where both viewers are a
 * row sized to the window and a wheel over the picture would otherwise do
 * nothing — and below that only once the picture is zoomed at all: a column
 * that scrolls on a phone-width window must keep scrolling over a picture
 * nobody has touched, and the pinch is still there to start. A double-click
 * goes in at the point and back out. A drag pans while there is anything to
 * pan. `+`, `-` and `0` are the keys, wired by the player through its
 * controls.
 *
 * **The transform is the whole of it.** `translate(x, y) scale(s)` on the
 * `<img>`, origin at the middle of the box — so zooming about a point `p`
 * (measured from the middle) keeps the picture point under it fixed:
 * `t' = p - (s'/s)(p - t)`. Nothing else is measured or moved, and the box,
 * the chrome and the transport are where they were.
 *
 * **The pan is clamped to the picture's edge.** At scale `s` the drawn
 * picture is `s` times its fitted size; while it is smaller than the box on
 * an axis it stays centred on that axis, and once it is larger it can be
 * pushed until its far edge meets the box's. A picture pushed clean off the
 * stage is a black box with nothing on it and no way to tell which way it
 * went.
 *
 * `touch-action` is `pan-y` at the fit and `none` once zoomed. The browser
 * gets the vertical scroll on a phone until the picture is the thing being
 * moved, and then it gets nothing — a drag that scrolled the column as well
 * as the picture is the failure both settings exist to stop. Pinch-zoom is
 * never the browser's here: the two-pointer path below is the pinch.
 */
/** Whether the viewer is the `md` row that does not scroll. jsdom has no `matchMedia`. */
function wideViewer(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(min-width: 768px)").matches
  );
}

export function useZoom({ container, media, enabled, value, onChange, resetKey }: Options) {
  const [inner, setInner] = useState<ZoomState>(FIT);
  const zoom = value ?? inner;

  // Read through a ref by every handler, so the wheel listener — attached
  // once, non-passive — sees the current state without re-attaching.
  const latest = useRef({ zoom, onChange, enabled });
  useEffect(() => {
    latest.current = { zoom, onChange, enabled };
  });

  const set = useCallback((next: ZoomState) => {
    const { onChange: notify } = latest.current;
    if (notify) notify(next);
    else setInner(next);
  }, []);

  /** The fitted picture's size in the box — what `object-contain` drew. */
  const fitted = useCallback((): { w: number; h: number } | null => {
    const box = container.current;
    const img = media.current;
    if (!box || !img || !img.naturalWidth || !img.naturalHeight) return null;
    const W = box.clientWidth;
    const H = box.clientHeight;
    if (!W || !H) return null;
    const ratio = Math.min(W / img.naturalWidth, H / img.naturalHeight);
    return { w: img.naturalWidth * ratio, h: img.naturalHeight * ratio };
  }, [container, media]);

  const clamp = useCallback(
    (next: ZoomState): ZoomState => {
      const scale = Math.min(MAX, Math.max(MIN, next.scale));
      if (scale === MIN) return FIT;
      const box = container.current;
      const size = fitted();
      if (!box || !size) return { scale, x: next.x, y: next.y };
      const maxX = Math.max(0, (size.w * scale - box.clientWidth) / 2);
      const maxY = Math.max(0, (size.h * scale - box.clientHeight) / 2);
      return {
        scale,
        x: Math.min(maxX, Math.max(-maxX, next.x)),
        y: Math.min(maxY, Math.max(-maxY, next.y)),
      };
    },
    [container, fitted],
  );

  /**
   * Zoom to `scale` about a point measured from the middle of the box —
   * `0,0` for the buttons and the keys, the pointer for a wheel or a
   * double-click, the fingers' midpoint for a pinch.
   */
  const zoomAbout = useCallback(
    (scale: number, px: number, py: number) => {
      const current = latest.current.zoom;
      const target = Math.min(MAX, Math.max(MIN, scale));
      const k = target / current.scale;
      set(
        clamp({
          scale: target,
          x: px - k * (px - current.x),
          y: py - k * (py - current.y),
        }),
      );
    },
    [clamp, set],
  );

  /** The pointer's place measured from the middle of the box. */
  const fromMiddle = useCallback(
    (clientX: number, clientY: number): [number, number] => {
      const box = container.current;
      if (!box) return [0, 0];
      const rect = box.getBoundingClientRect();
      return [clientX - rect.left - rect.width / 2, clientY - rect.top - rect.height / 2];
    },
    [container],
  );

  const zoomIn = useCallback(
    () => zoomAbout(latest.current.zoom.scale * STEP, 0, 0),
    [zoomAbout],
  );
  const zoomOut = useCallback(
    () => zoomAbout(latest.current.zoom.scale / STEP, 0, 0),
    [zoomAbout],
  );
  const reset = useCallback(() => set(FIT), [set]);

  // Stepping to another picture starts it at the fit. Uncontrolled only: a
  // controlled stage decides for itself when its pair resets.
  const lastKey = useRef(resetKey);
  useEffect(() => {
    if (lastKey.current === resetKey) return;
    lastKey.current = resetKey;
    if (!value) setInner(FIT);
  }, [resetKey, value]);

  /**
   * The wheel, attached by hand and non-passive.
   *
   * React registers `wheel` as passive, so a handler in JSX cannot
   * `preventDefault` — and a pinch on a trackpad that is not prevented is the
   * browser zooming the whole page. The rule: a pinch (`ctrlKey`, which is how
   * a trackpad pinch arrives; `metaKey` for the keyboard's version) always
   * zooms; a plain wheel zooms from `md`, where the viewer is a row that does
   * not scroll, and below it only once the picture is already zoomed, so a
   * scrolling column keeps its scroll over a picture at the fit. `md` is the
   * viewers' own breakpoint (`ViewerFrame`), read here as a media query.
   */
  useEffect(() => {
    const box = container.current;
    if (!box || !enabled) return;
    const onWheel = (event: WheelEvent) => {
      const { zoom: current } = latest.current;
      const pinch = event.ctrlKey || event.metaKey;
      if (!pinch && current.scale === MIN && !wideViewer()) return;
      event.preventDefault();
      // A pinch's delta is small and fine-grained; a wheel's comes in notches
      // of 100. Same curve, so a notch is about ×1.2 and a pinch is smooth.
      const factor = Math.exp(-event.deltaY * WHEEL * (pinch ? 5 : 1));
      const [px, py] = fromMiddle(event.clientX, event.clientY);
      zoomAbout(current.scale * factor, px, py);
    };
    box.addEventListener("wheel", onWheel, { passive: false });
    return () => box.removeEventListener("wheel", onWheel);
  }, [container, enabled, fromMiddle, zoomAbout]);

  /**
   * Pointers, for the drag and the pinch.
   *
   * One pointer down on a zoomed picture is a pan; two down anywhere is a
   * pinch, zooming about the fingers' midpoint by the change in their
   * distance and panning by the midpoint's travel. The pointers are held in
   * a map so a finger lifting mid-pinch leaves the other one panning rather
   * than jumping.
   */
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ dist: number; mid: [number, number] } | null>(null);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (!latest.current.enabled) return;
      if (event.pointerType === "mouse" && event.button !== 0) return;
      // A press on the chrome is the chrome's. Capturing it here would
      // redirect the pointer-up to the box, and the click that follows lands
      // on the box too — the zoom buttons stopped working the moment the
      // picture was zoomed, which is exactly when they are wanted.
      if ((event.target as HTMLElement | null)?.closest("button, a, input, [role=slider]")) return;
      const map = pointers.current;
      map.set(event.pointerId, { x: event.clientX, y: event.clientY });
      // Only capture when there is something to drag: a press on a picture at
      // the fit is a click, and capturing it would swallow a double-click.
      if (map.size === 1 && latest.current.zoom.scale === MIN && event.pointerType === "mouse")
        return;
      event.currentTarget.setPointerCapture(event.pointerId);
      if (map.size === 2) {
        const [a, b] = [...map.values()] as [{ x: number; y: number }, { x: number; y: number }];
        gesture.current = {
          dist: Math.hypot(a.x - b.x, a.y - b.y),
          mid: [(a.x + b.x) / 2, (a.y + b.y) / 2],
        };
      } else if (latest.current.zoom.scale > MIN) {
        setDragging(true);
      }
    },
    [],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const map = pointers.current;
      const was = map.get(event.pointerId);
      if (!was) return;
      map.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const current = latest.current.zoom;

      if (map.size >= 2 && gesture.current) {
        const [a, b] = [...map.values()] as [{ x: number; y: number }, { x: number; y: number }];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        const mid: [number, number] = [(a.x + b.x) / 2, (a.y + b.y) / 2];
        const prior = gesture.current;
        gesture.current = { dist, mid };
        if (!prior.dist) return;
        const [px, py] = fromMiddle(mid[0], mid[1]);
        const k = dist / prior.dist;
        set(
          clamp({
            scale: current.scale * k,
            x: px - k * (px - current.x) + (mid[0] - prior.mid[0]),
            y: py - k * (py - current.y) + (mid[1] - prior.mid[1]),
          }),
        );
        return;
      }

      if (current.scale === MIN) return;
      set(
        clamp({
          scale: current.scale,
          x: current.x + (event.clientX - was.x),
          y: current.y + (event.clientY - was.y),
        }),
      );
    },
    [clamp, fromMiddle, set],
  );

  const onPointerUp = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const map = pointers.current;
    map.delete(event.pointerId);
    if (map.size < 2) gesture.current = null;
    if (map.size === 0) setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  const onDoubleClick = useCallback(
    (event: ReactMouseEvent<HTMLElement>) => {
      if (!latest.current.enabled) return;
      const current = latest.current.zoom;
      if (current.scale > MIN) {
        reset();
        return;
      }
      const [px, py] = fromMiddle(event.clientX, event.clientY);
      zoomAbout(DOUBLE, px, py);
    },
    [fromMiddle, reset, zoomAbout],
  );

  const zoomed = zoom.scale > MIN;

  const style = useMemo<CSSProperties>(
    () => ({
      transform: zoomed
        ? `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})`
        : undefined,
      transformOrigin: "center center",
    }),
    [zoom.scale, zoom.x, zoom.y, zoomed],
  );

  const stage = useMemo<CSSProperties>(
    () => ({
      touchAction: enabled ? (zoomed ? "none" : "pan-y") : undefined,
      cursor: !enabled || !zoomed ? undefined : dragging ? "grabbing" : "grab",
    }),
    [dragging, enabled, zoomed],
  );

  return {
    zoom,
    zoomed,
    /** What the `<img>` wears. */
    style,
    /** What the box wears — the cursor and `touch-action`. */
    stage,
    zoomIn,
    zoomOut,
    reset,
    canZoomIn: enabled && zoom.scale < MAX,
    canZoomOut: enabled && zoomed,
    handlers: enabled
      ? {
          onPointerDown,
          onPointerMove,
          onPointerUp,
          onPointerCancel: onPointerUp,
          onDoubleClick,
        }
      : {},
  };
}
