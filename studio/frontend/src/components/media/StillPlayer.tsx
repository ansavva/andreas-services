import { useCallback, useEffect, useRef, type CSSProperties, type DragEvent } from "react";

import { IconButton, Text } from "@ansavva/design-system";

import type { AttachRef } from "../../context/CreateBarContext";
import { objectRef, startNodeDrag } from "../create/dragRef";
import { useFullscreen } from "../../hooks/useFullscreen";
import { useSignedSrc } from "../../hooks/useSignedSrc";
import {
  CloseIcon,
  FullscreenEnterIcon,
  FullscreenExitIcon,
  ZoomInIcon,
  ZoomOutIcon,
} from "../common/icons";
import { useViewerFrameLift } from "../viewer/ViewerFrame";
import {
  ASPECTS,
  CHROME_SCRIM,
  FITS,
  FULLSCREEN_TOP,
  Unavailable,
  type MediaPlayerControls,
  type MediaPlayerProps,
} from "./playerShell";
import { useZoom } from "./useZoom";

type StillPlayerProps = Omit<MediaPlayerProps, "isVideo" | "autoPlay" | "startMuted">;

/**
 * A still, shown where it sits: zoom, fullscreen, and a drag to the sheet.
 *
 * **The one player that is still ours**, because no video library does
 * pictures. `ClipPlayer` is Video.js; this keeps `useZoom` and `useFullscreen`,
 * and `useFullscreen` keeps its in-app fallback for the one reason it ever
 * had — Safari on iOS refuses `requestFullscreen` on anything but a
 * `<video>`, and a picture has no `<video>` to hand the phone.
 */
export function StillPlayer({
  nodeId,
  url,
  name = "",
  aspect = "video",
  fit = "contain",
  className = "",
  onClose,
  onContainerChange,
  onControlsChange,
  onFullscreenChange,
  overlay,
  actions,
  zoomable = false,
  zoom: zoomValue,
  onZoomChange,
  drag = true,
}: StillPlayerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

  // Held in a ref so a caller passing an inline arrow does not change the
  // identity of the ref callback below, which would detach and re-attach the
  // container on every render.
  const onContainerChangeRef = useRef(onContainerChange);
  useEffect(() => {
    onContainerChangeRef.current = onContainerChange;
  });

  const { src, failed, onError } = useSignedSrc(nodeId, url);
  const { isFullscreen, native, toggle } = useFullscreen(containerRef);
  const zoom = useZoom({
    container: containerRef,
    media: imageRef,
    enabled: zoomable,
    value: zoomValue,
    onChange: onZoomChange,
    resetKey: nodeId,
  });

  /**
   * Reported straight out of the ref callback rather than through state.
   *
   * A state mirror would report `null` on the first commit and the element only
   * on the render after it — the effect reading it closes over the previous
   * value — and would report nothing at all on unmount, because a `setState` on
   * an unmounting component is dropped. From here the caller sees exactly what
   * React saw, when React saw it, in both directions.
   */
  const setContainerNode = useCallback((element: HTMLDivElement | null) => {
    containerRef.current = element;
    onContainerChangeRef.current?.(element);
  }, []);

  /**
   * Escape leaves the app's own fullscreen before anything else hears it.
   *
   * The browser's fullscreen answers Escape itself; the fallback is an ordinary
   * element, so without this the key would reach the screen underneath and
   * close the whole run — leaving the reader two steps from where one press
   * should have put them. Capture phase, for the same reason.
   */
  useEffect(() => {
    if (!isFullscreen || native) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      void toggle();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [isFullscreen, native, toggle]);

  // Reported on change only, through a ref, so an inline arrow from the
  // caller neither re-subscribes nor fires on every render.
  const onFullscreenChangeRef = useRef(onFullscreenChange);
  useEffect(() => {
    onFullscreenChangeRef.current = onFullscreenChange;
  });
  useEffect(() => {
    onFullscreenChangeRef.current?.(isFullscreen);
  }, [isFullscreen]);

  // The frame this sits in, if any, has to climb past the header while the
  // app's own fullscreen is up — see `ViewerFrame`. Native needs nothing:
  // the browser paints the fullscreen element over everything itself.
  const lift = useViewerFrameLift();
  useEffect(() => {
    const app = isFullscreen && !native;
    lift(app);
    return () => {
      if (app) lift(false);
    };
  }, [isFullscreen, native, lift]);

  const close = useCallback(() => {
    if (isFullscreen) void toggle();
    onClose?.();
  }, [isFullscreen, onClose, toggle]);

  /**
   * The controls a keyboard shortcut needs, handed up once.
   *
   * Everything they touch is read through `latest` rather than closed over, so
   * the object below is created on mount and never again — a caller holding it
   * in state (which is how `ObjectPage` gets it to `useKeyboardNav`) would
   * otherwise re-render on every zoom, and re-registering would loop.
   */
  const onControlsChangeRef = useRef(onControlsChange);
  const latest = useRef({ toggle, zoom });
  useEffect(() => {
    onControlsChangeRef.current = onControlsChange;
    latest.current = { toggle, zoom };
  });

  useEffect(() => {
    const controls: MediaPlayerControls = {
      // Nothing plays on a still.
      togglePlay: () => undefined,
      pause: () => undefined,
      currentTime: () => 0,
      toggleMuted: () => undefined,
      toggleFullscreen: () => void latest.current.toggle(),
      zoomIn: () => latest.current.zoom.zoomIn(),
      zoomOut: () => latest.current.zoom.zoomOut(),
      zoomReset: () => latest.current.zoom.reset(),
    };
    onControlsChangeRef.current?.(controls);
    return () => onControlsChangeRef.current?.(null);
  }, []);

  /**
   * Fullscreen is for viewing. Zoom, and out again — nothing about the file.
   * The caller's `actions` and the player's own Close wait outside it.
   */
  const fileChrome = !isFullscreen;
  const shownActions = fileChrome ? actions : undefined;

  // A still at the fit drags to the sheet; zoomed, the same gesture is the
  // pan — see `useZoom`. The chrome's buttons never start one: a press on a
  // button is not a drag whatever the box says.
  const draggable = drag !== false && !failed && !zoom.zoomed;
  const onDragStart = (event: DragEvent) => {
    if ((event.target as HTMLElement | null)?.closest("button, a, input")) {
      event.preventDefault();
      return;
    }
    startNodeDrag(event, drag === true ? objectRef(nodeId, url, name) : (drag as AttachRef));
  };

  const media = `h-full w-full ${FITS[fit]}`;
  const box = [
    // **`overflow-clip`, not `-hidden`, and the zoom is why.** `hidden` still
    // makes the box a scroll container, and a zoomed picture's overflow to the
    // right and bottom counts as scrollable — so the browser, bringing a
    // focused chrome button into view, scrolled the box by a quarter of the
    // picture and the zoom landed off-centre. `clip` clips and cannot scroll.
    "isolate block overflow-clip bg-overlay-scrim",
    isFullscreen ? "" : ASPECTS[aspect],
    // **The app positions the box only when the browser has not.** Native
    // fullscreen makes the element the whole screen by itself; the fallback is
    // an ordinary element that has to be told, and it has to sit above the
    // sheet and the header (`z-30` both).
    //
    // **One position class, never two.** This used to be `relative` always
    // and `fixed` added on top, and Tailwind emits `relative` after `fixed`,
    // so the fallback box stayed exactly where the page had put it — with a
    // screen's width and height hanging off that corner. On an iPhone, the
    // one device that only has the fallback, "maximize" enlarged the box into
    // the header and off the right edge and covered nothing.
    isFullscreen && !native ? "fixed inset-0 z-50 w-screen" : "relative",
    isFullscreen ? "" : className,
  ].join(" ");

  /**
   * `100dvh`, never `inset-0`, and the reel paid for this one.
   *
   * The page asks for `viewport-fit=cover`, so a box pinned to all four sides
   * is laid out against the *large* viewport — the one with the browser's
   * toolbars hidden — and mobile Safari then draws its bottom toolbar over the
   * result. Whatever sits on that edge cannot be pressed. The dynamic viewport
   * shrinks and grows with those toolbars, so the player ends where the usable
   * screen ends.
   */
  const shell: CSSProperties | undefined = isFullscreen
    ? { height: "100dvh", maxHeight: "100dvh" }
    : undefined;

  return (
    <div
      ref={setContainerNode}
      className={box}
      style={{ ...shell, ...zoom.stage }}
      // Which fullscreen is in force, for anything reading the DOM — a test,
      // a script. What has to make way for it is told in code, above.
      data-fullscreen={isFullscreen ? (native ? "native" : "app") : undefined}
      draggable={draggable || undefined}
      onDragStart={draggable ? onDragStart : undefined}
      {...zoom.handlers}
    >
      {failed ? (
        <Unavailable />
      ) : (
        <img
          ref={imageRef}
          src={src}
          alt={name}
          onError={onError}
          decoding="async"
          loading="lazy"
          draggable={false}
          className={media}
          style={zoom.style}
        />
      )}

      {/*
        **No scrim across the picture — each control carries its own.**

        This row used to sit on a `from-overlay-scrim/80` gradient forty pixels
        deep, drawn over every still all the time, so the top of every picture
        in the app was under a dark band. It was there to keep a white glyph
        legible on a pale frame; a pill behind each glyph does that over the
        two dozen pixels the glyph occupies instead of over the whole width of
        the picture. The tile menus and the favorite heart already do it that
        way.
      */}
      {!failed && (
        <div
          className={`pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start
                      justify-between gap-2 p-2 ${isFullscreen ? FULLSCREEN_TOP : ""}`}
        >
          <div className="pointer-events-auto flex min-w-0 items-center gap-1">{shownActions}</div>

          <div className="pointer-events-auto flex shrink-0 items-center gap-1">
            {/*
              **Zoom before everything else in the row.** Two glyphs and —
              once the picture is in at all — the figure, so a person can see
              they are not at the fit. Every gesture `useZoom` answers gets
              here too; these are the two a pointer can find.
            */}
            {zoomable && (
              <>
                <IconButton
                  label="Zoom out (-)"
                  size="sm"
                  onClick={zoom.zoomOut}
                  disabled={!zoom.canZoomOut}
                  intent="overlay"
                  className={CHROME_SCRIM}
                >
                  <ZoomOutIcon />
                </IconButton>
                {zoom.zoomed && (
                  <Text
                    variant="caption"
                    family="mono"
                    aria-label="Zoom level"
                    className={`${CHROME_SCRIM} px-1.5 py-0.5 tabular-nums text-overlay-ink`}
                  >
                    {Math.round(zoom.zoom.scale * 100)}%
                  </Text>
                )}
                <IconButton
                  label="Zoom in (+)"
                  size="sm"
                  onClick={zoom.zoomIn}
                  disabled={!zoom.canZoomIn}
                  intent="overlay"
                  className={CHROME_SCRIM}
                >
                  <ZoomInIcon />
                </IconButton>
              </>
            )}

            {/*
              **Always offered.** It used to be drawn only where
              `requestFullscreen` works, which meant never on an iPhone —
              Safari refuses it on anything but a `<video>` — so the one device
              where a picture is smallest was the one with no way to enlarge
              it. `useFullscreen` falls back to an in-app expansion there.
            */}
            <IconButton
              label={isFullscreen ? "Exit fullscreen (f)" : "Fullscreen (f)"}
              size="sm"
              onClick={() => void toggle()}
              intent="overlay"
              className={CHROME_SCRIM}
            >
              {isFullscreen ? <FullscreenExitIcon /> : <FullscreenEnterIcon />}
            </IconButton>

            {fileChrome && onClose && (
              <IconButton
                label="Close"
                size="sm"
                onClick={close}
                intent="overlay"
                className={CHROME_SCRIM}
              >
                <CloseIcon />
              </IconButton>
            )}
          </div>
        </div>
      )}

      {overlay}
    </div>
  );
}
