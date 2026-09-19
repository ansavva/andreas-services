import "@videojs/react/video/skin.css";

import { useEffect, useRef, type CSSProperties, type RefObject } from "react";

import { selectFullscreen, useContainer, usePlayer as useStore } from "@videojs/react";
import { Video, VideoPlayer, VideoSkin, usePlayer } from "@videojs/react/video";

import { useNearViewport } from "../../hooks/useNearViewport";
import { useSignedSrc } from "../../hooks/useSignedSrc";
import {
  ASPECTS,
  Unavailable,
  type MediaPlayerControls,
  type MediaPlayerProps,
} from "./playerShell";

/**
 * A clip, on Video.js v10's own player — the packaged skin, as shipped.
 *
 * **Nothing of ours is drawn inside it.** `VideoSkin` is the whole surface:
 * play, seek with thumbnails, volume, mute, captions, playback speed,
 * picture-in-picture, AirPlay and Cast, fullscreen, the settings menu, the
 * keyboard shortcuts (Space, `k`, `m`, `f`, `j`/`l`, arrows, digits, `<`/`>`)
 * and the tap and double-tap gestures. Whatever the package adds next
 * arrives here with the version bump. The first cut composed the package's
 * primitives into a copy of the transport we used to hand-roll; that threw
 * away exactly the features a library is for.
 *
 * **The app's own controls live outside it.** `actions` — a `Frame` menu, a
 * compare label — are drawn in a row above the player, not over the picture,
 * so the skin's layout is the skin's. They are outside the fullscreen element
 * too, which matches what they were before: fullscreen is for looking.
 *
 * **Fullscreen is the package's.** It fullscreens the skin's container where
 * the element API exists (a laptop, iOS 26's Safari) and hands the `<video>`
 * to `webkitSetPresentationMode` where it does not, which is the phone's own
 * player: Safari's bar gone, PiP, AirPlay, speed. What used to be here — an
 * in-app box under Safari's bar — is gone for clips; a still keeps it,
 * because a picture has no `<video>` to hand the phone.
 *
 * What remains ours is the seam around the player: the signed `src` and its
 * re-sign on expiry, withholding `src` until the box is near the viewport,
 * the container handed up for a dialog to portal into, and the controls
 * handed up for the page's keys (which only fire when focus is *outside*
 * the player — see `useKeyboardNav`).
 */

type ClipPlayerProps = Omit<
  MediaPlayerProps,
  "isVideo" | "zoomable" | "zoom" | "onZoomChange" | "drag" | "onClose"
>;

export function ClipPlayer({
  nodeId,
  url,
  aspect = "video",
  fit = "contain",
  autoPlay = false,
  startMuted = true,
  className = "",
  onContainerChange,
  onControlsChange,
  onFullscreenChange,
  overlay,
  actions,
}: ClipPlayerProps) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const { src, failed, onError } = useSignedSrc(nodeId, url);
  const near = useNearViewport(boxRef, true);

  /**
   * The three public seams the skin exposes for a brand, and no more: the
   * face (the app's body font, where the skin would reach for Inter), how the
   * picture fills the box (`fit`), and the frame's corner. Colours stay the
   * skin's — its controls are dark in both schemes, and the app's primary
   * role is the *ink* of the scheme, which would be black on them in light
   * mode.
   *
   * The corner is `--media-border-radius`, the value the skin's own
   * `--media-video-border-radius` falls back on (28px otherwise) — set here
   * and not on the derived variable, because the skin zeroes the derived one
   * under `:fullscreen` and an inline value on the same element would win
   * over that. `lg` is the app's largest step, and what the still stage
   * beside this wears; the controls are untouched.
   */
  const skin = {
    "--media-font-family": "var(--font-body)",
    "--media-object-fit": fit,
    "--media-border-radius": "var(--radius-lg)",
  } as CSSProperties;

  return (
    <div ref={boxRef} className="flex h-full min-h-0 w-full flex-col gap-2">
      {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}

      {failed ? (
        <div className={`min-h-0 flex-1 bg-overlay-scrim ${ASPECTS[aspect]} ${className}`}>
          <Unavailable />
        </div>
      ) : (
        <VideoPlayer>
          <VideoSkin
            style={skin}
            // `min-h-0 flex-1` fills a caller-sized box (`aspect="auto"`);
            // otherwise the ratio sizes it and the caller's box is whatever
            // the page column gives.
            className={`min-h-0 flex-1 ${ASPECTS[aspect]} ${className}`}
          >
            <Video
              ref={videoRef}
              // Withheld until the box is near the viewport — what stops sixty
              // range requests on a folder of sixty clips. `metadata` is how the
              // first frame and the duration arrive for free.
              src={near || autoPlay ? src : undefined}
              onError={onError}
              autoPlay={autoPlay}
              muted={startMuted}
              loop
              playsInline
              preload="metadata"
            />
            <Seams
              videoRef={videoRef}
              onContainerChange={onContainerChange}
              onControlsChange={onControlsChange}
              onFullscreenChange={onFullscreenChange}
            />
            {overlay}
          </VideoSkin>
        </VideoPlayer>
      )}
    </div>
  );
}

/**
 * Inside the player, where the store is. Renders nothing; reports three
 * things to the page and hands its keys a way in.
 */
function Seams({
  videoRef,
  onContainerChange,
  onControlsChange,
  onFullscreenChange,
}: Pick<ClipPlayerProps, "onContainerChange" | "onControlsChange" | "onFullscreenChange"> & {
  videoRef: RefObject<HTMLVideoElement | null>;
}) {
  const player = usePlayer();
  const isFullscreen = useStore(selectFullscreen)?.fullscreen ?? false;
  const container = useContainer();

  // Each callback is read through a ref, so an inline arrow from the caller
  // neither re-subscribes nor fires on every tick of the clock.
  const callbacks = useRef({ onContainerChange, onControlsChange, onFullscreenChange });
  useEffect(() => {
    callbacks.current = { onContainerChange, onControlsChange, onFullscreenChange };
  });

  /**
   * The skin's container is the fullscreen element, and the one a dialog has
   * to portal into to be painted while it is up. Reported as the package
   * learns of it, and `null` again on the way out.
   */
  useEffect(() => {
    callbacks.current.onContainerChange?.(container);
    return () => callbacks.current.onContainerChange?.(null);
  }, [container]);

  useEffect(() => {
    callbacks.current.onFullscreenChange?.(isFullscreen);
  }, [isFullscreen]);

  /**
   * The verbs a page's keys need. One object for the life of the player, so a
   * caller holding it in state (which is how `ObjectPage` gets it to
   * `useKeyboardNav`) does not re-render on every tick.
   */
  const latest = useRef(player);
  latest.current = player;
  useEffect(() => {
    const controls: MediaPlayerControls = {
      togglePlay: () => void latest.current.togglePaused(),
      pause: () => latest.current.pause(),
      currentTime: () => videoRef.current?.currentTime ?? 0,
      toggleMuted: () => void latest.current.toggleMuted(),
      toggleFullscreen: () => void latest.current.toggleFullscreen(),
      // No-ops on a clip: zoom is a still's.
      zoomIn: () => undefined,
      zoomOut: () => undefined,
      zoomReset: () => undefined,
    };
    callbacks.current.onControlsChange?.(controls);
    return () => callbacks.current.onControlsChange?.(null);
  }, [videoRef]);

  return null;
}
