import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

import { IconButton, Text } from "@ansavva/design-system";

import { useFullscreen } from "../../hooks/useFullscreen";
import { useMediaPlayback } from "../../hooks/useMediaPlayback";
import { useNearViewport } from "../../hooks/useNearViewport";
import { useSignedSrc } from "../../hooks/useSignedSrc";
import { formatDuration } from "../../utils/format";
import {
  CloseIcon,
  FullscreenEnterIcon,
  FullscreenExitIcon,
  PlayIcon,
  SoundOffIcon,
  SoundOnIcon,
} from "../common/icons";
import { CHROME_BUTTON } from "./chromeButton";
import { PlayerTransport } from "./PlayerTransport";

/**
 * Every class here is a whole literal, for the reason `MediaThumb` spells out:
 * Tailwind finds classes by scanning source text, so anything assembled from a
 * template literal compiles to no CSS at all.
 */
const ASPECTS = {
  square: "aspect-square",
  portrait: "aspect-[3/4]",
  video: "aspect-video",
  /** No ratio of its own — the caller sized the box. */
  auto: "",
} as const;

const FITS = { cover: "object-cover", contain: "object-contain" } as const;

/**
 * Padding that clears a notch, a home indicator and a landscape bezel — and
 * ONLY while the player owns the screen.
 *
 * Inline in a page column these insets are wrong rather than merely unused: a
 * landscape iPhone reports `safe-area-inset-left: 44px`, which would put 44px
 * of padding inside a 300px-wide player sitting nowhere near the bezel. The
 * page's own layout is what keeps an inline player clear of an edge; these two
 * strings are for the fullscreen element, which has no layout above it.
 */
const FULLSCREEN_TOP = "pt-[max(0.5rem,env(safe-area-inset-top))]";
const FULLSCREEN_BOTTOM =
  "pb-[max(0.75rem,env(safe-area-inset-bottom))] pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))]";

/**
 * The three things a keyboard shortcut needs and the DOM cannot reach.
 *
 * Play, mute and fullscreen all live behind state this component owns —
 * `playing`, `useMediaPlayback`'s `muted`, `useFullscreen`'s element — so a
 * page that binds Space, `m` and `f` cannot press them by finding a button and
 * clicking it: the labels would become an API, and a mute set on the element
 * behind the hook's back desynchronises the icon from the sound. This is that
 * API, stated once.
 *
 * `togglePlay` is deliberately one verb rather than two. From the poster it
 * *starts* playback (which mounts it); once playing it pauses and resumes.
 * "Space plays" means the same thing to a person in both states.
 */
export interface MediaPlayerControls {
  togglePlay: () => void;
  toggleMuted: () => void;
  toggleFullscreen: () => void;
}

interface MediaPlayerProps {
  /**
   * The node id, which is what a re-sign addresses.
   *
   * Not the key: `/api/asset` signs by node, and a name path would leave every
   * expired tile broken for anything uploaded through the app. It is also the
   * playback key, so one player is one node.
   */
  nodeId: string;
  /** Presigned inline GET. Re-signed through `useSignedSrc` when it expires. */
  url: string;
  /** What the file is called. Names the play and close controls. */
  name: string;
  isVideo?: boolean;
  /** The poster box's ratio. `auto` where the caller sized the box itself. */
  aspect?: keyof typeof ASPECTS;
  /**
   * `contain` by default, where `MediaThumb` defaults to `cover`.
   *
   * A player is where a frame is judged, and the bucket mixes 1:1, 9:16 and
   * 16:9 output from the same run family — cropping to fill would hide exactly
   * the thing being looked at.
   */
  fit?: "cover" | "contain";
  /** Skip the poster and mount playback on first render. */
  autoPlay?: boolean;
  /**
   * Whether playback starts silent. Defaults to true, and that is a browser
   * rule rather than a preference — see the note in the body.
   */
  startMuted?: boolean;
  /** Extra classes for the box: borders and rounding, which vary by surface. */
  className?: string;
  /**
   * Fires when the viewer closes playback back to the poster, after the player
   * has already done so. Not a request to unmount — the player stays.
   */
  onClose?: () => void;
  /**
   * The player's own container element, as it mounts and unmounts.
   *
   * **This is the seam that lets a dialog open inside fullscreen.** The
   * Fullscreen API paints only the fullscreen element and its descendants, so
   * anything portalled to `<body>` is invisible while one is up — which is why
   * six files in this app hand-roll an inline dialog. Pass this element to
   * `Dialog.Root` / `Drawer.Root` / `AlertDialog.Root`'s `container` prop and
   * the portal lands inside the player instead.
   */
  onContainerChange?: (element: HTMLElement | null) => void;
  /**
   * The player's controls, as they become available and as they go.
   *
   * For a caller that binds keys — `ObjectPage` binds Space, `m` and `f`. Held
   * in state the same way `onContainerChange`'s element is; the object handed
   * over keeps one identity for the life of the player, so storing it does not
   * loop.
   */
  onControlsChange?: (controls: MediaPlayerControls | null) => void;
  /**
   * Chrome drawn inside the player, above the media and below the transport.
   *
   * Rendered as a descendant of the container, so it is painted in fullscreen
   * too. The caller positions it; the player only guarantees the stacking
   * context.
   */
  overlay?: ReactNode;
  /** Extra buttons at the left of the top chrome row — download, delete, rename. */
  actions?: ReactNode;
}

/**
 * One image or video, played where it sits.
 *
 * **The affordance studio has never had is `close`.** Judging a cut used to
 * mean leaving the page it belongs to for a full-viewport reel; here the first
 * press mounts playback in the same box, and the close button puts the poster
 * back. Nothing navigates.
 *
 * Three sizes, one component: inline in a page column, filling the object
 * screen, and filling the fullscreen element. What changes between them is the
 * box the caller gives it and the `size` the transport is drawn at — there is
 * no `variant`, because a second layout is the thing that made the lightbox and
 * the reel drift apart.
 *
 * Two disciplines carried over rather than reinvented:
 *
 * * **No `src` until the box is within a viewport** (`useNearViewport`). It is
 *   what stops sixty range requests on a folder of sixty clips, and
 *   `preload="metadata"` is how the poster frame arrives for free out of a
 *   bucket that ships no derivatives.
 * * **One `<video>` element for both states.** The poster and the playing
 *   surface are the same element, so pressing play starts what is already
 *   loaded rather than re-fetching it, and closing hands the element back to
 *   `useMediaPlayback`'s own "everything that is not current is paused and
 *   rewound" effect — which is what makes close return to frame zero.
 *
 * **Sound starts off, and that is the autoplay policy rather than a taste.**
 * The `<video>` does not exist during the click that presses play, so its
 * `muted` cannot be cleared inside that gesture — and setting it from the
 * effect that follows is bug #1 in `useMediaPlayback`'s header, the one that
 * reads as "the unmute button does nothing". The mute button is a real gesture
 * on a mounted element, which is the path that hook was built for. A caller
 * that would rather gamble on sticky activation can pass `startMuted={false}`;
 * a refusal still lands as `blocked` and plays on silently.
 */
export function MediaPlayer({
  nodeId,
  url,
  name,
  isVideo = false,
  aspect = "video",
  fit = "contain",
  autoPlay = false,
  startMuted = true,
  className = "",
  onClose,
  onContainerChange,
  onControlsChange,
  overlay,
  actions,
}: MediaPlayerProps) {
  const [playing, setPlaying] = useState(autoPlay);
  const [posterDuration, setPosterDuration] = useState<number | null>(null);
  const [buffered, setBuffered] = useState<number | undefined>(undefined);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Held in a ref so a caller passing an inline arrow does not change the
  // identity of the ref callback below, which would detach and re-attach the
  // container on every render.
  const onContainerChangeRef = useRef(onContainerChange);
  useEffect(() => {
    onContainerChangeRef.current = onContainerChange;
  });

  const { src, failed, onError } = useSignedSrc(nodeId, url);
  const near = useNearViewport(containerRef, isVideo);
  const { isFullscreen, supported, toggle } = useFullscreen(containerRef);

  // The key is the node, and it is `undefined` while the poster is up — which
  // is the whole of "closed" as far as playback is concerned: the hook pauses
  // and rewinds everything that is not current.
  const playback = useMediaPlayback(playing ? nodeId : undefined);
  const { register } = playback;

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
   * `register` is memoised per key inside the hook precisely so a ref callback
   * keeps one identity across a re-render; composing it inline would hand React
   * a new function on every tick of the scrub bar and detach the element sixty
   * times a second.
   */
  const registerVideo = register(nodeId);
  const setVideoNode = useCallback(
    (element: HTMLVideoElement | null) => {
      videoRef.current = element;
      registerVideo(element);
    },
    [registerVideo],
  );

  /**
   * How far the browser has read ahead, for the seek bar's second fill.
   *
   * Read from the element rather than added to `useMediaPlayback`: it is
   * decoration, it is the only thing here that wants `progress`, and that hook
   * documents three separately-fixed bugs that nothing should be edited around.
   */
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !playing) return;

    const read = () => {
      try {
        const ranges = video.buffered;
        setBuffered(ranges.length > 0 ? ranges.end(ranges.length - 1) : 0);
      } catch {
        // jsdom, and anything else that declares `buffered` without meaning it.
        setBuffered(undefined);
      }
    };

    video.addEventListener("progress", read);
    video.addEventListener("timeupdate", read);
    read();
    return () => {
      video.removeEventListener("progress", read);
      video.removeEventListener("timeupdate", read);
    };
  }, [playing]);

  const startPlaying = useCallback(() => {
    if (!startMuted) {
      // Inside the gesture, before the element exists: this only records the
      // preference, and the mount effect is what applies it. Off by default —
      // see the component's header for why.
      playback.toggleMuted();
    }
    setPlaying(true);
  }, [playback, startMuted]);

  const close = useCallback(() => {
    if (isFullscreen) void toggle();
    setPlaying(false);
    onClose?.();
  }, [isFullscreen, onClose, toggle]);

  /**
   * The three controls a keyboard shortcut needs, handed up once.
   *
   * Everything they touch is read through `latest` rather than closed over, so
   * the object below is created on mount and never again — a caller holding it
   * in state (which is how `ObjectPage` gets it to `useKeyboardNav`) would
   * otherwise re-render on every tick of the scrub bar, and re-registering
   * would loop.
   */
  const onControlsChangeRef = useRef(onControlsChange);
  const latest = useRef({ isVideo, playing, startPlaying, playback, toggle });
  useEffect(() => {
    onControlsChangeRef.current = onControlsChange;
    latest.current = { isVideo, playing, startPlaying, playback, toggle };
  });

  useEffect(() => {
    const controls: MediaPlayerControls = {
      togglePlay: () => {
        const now = latest.current;
        if (!now.isVideo) return;
        // From the poster, "play" is the press that mounts playback at all.
        if (now.playing) now.playback.togglePaused();
        else now.startPlaying();
      },
      toggleMuted: () => latest.current.playback.toggleMuted(),
      toggleFullscreen: () => void latest.current.toggle(),
    };
    onControlsChangeRef.current?.(controls);
    return () => onControlsChangeRef.current?.(null);
  }, []);

  const showChrome = playing || !isVideo || isFullscreen;
  const duration = playback.duration || posterDuration || 0;

  const media = `h-full w-full ${FITS[fit]}`;
  const box = [
    "relative isolate block overflow-hidden rounded-none bg-chrome-scrim",
    isFullscreen ? "" : ASPECTS[aspect],
    className,
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
    <div ref={setContainerNode} className={box} style={shell}>
      {failed ? (
        <div className="flex h-full w-full items-center justify-center p-6 text-center">
          <Text variant="caption" tone="muted">
            This file could not be loaded. It may have been removed from the bucket.
          </Text>
        </div>
      ) : isVideo ? (
        <video
          ref={setVideoNode}
          // Withheld until the box is near the viewport, and unconditional once
          // playing — a press is not a moment to start waiting for an observer.
          src={near || playing ? src : undefined}
          onError={onError}
          onLoadedMetadata={(event) => setPosterDuration(event.currentTarget.duration)}
          // No `autoplay` attribute and no `controls`: `useMediaPlayback` starts
          // it from the key, and the transport below is ours so that the
          // browser's own bar cannot sit under a phone's toolbar.
          loop
          muted={playback.muted}
          playsInline
          preload={playing ? "auto" : "metadata"}
          className={media}
        />
      ) : (
        <img
          src={src}
          alt={name}
          onError={onError}
          decoding="async"
          loading="lazy"
          className={media}
        />
      )}

      {/* The poster's press target is the whole box, which is the size a finger
          wants. The circle is what says it is pressable. */}
      {isVideo && !playing && !failed && (
        // eslint-disable-next-line studio/no-hand-rolled-button -- a full-bleed hit target the size of the frame.
        <button
          type="button"
          onClick={startPlaying}
          aria-label={`Play ${name}`}
          className="absolute inset-0 z-10 flex cursor-pointer items-center justify-center
                     bg-chrome-scrim/20 transition-colors hover:bg-chrome-scrim/40
                     focus-visible:outline-2 focus-visible:outline-offset-[-2px]
                     focus-visible:outline-primary"
        >
          <span className="flex size-14 items-center justify-center rounded-pill bg-chrome-scrim/70 text-chrome-ink">
            <PlayIcon className="size-7 fill-none stroke-current stroke-[1.5]" />
          </span>
        </button>
      )}

      {/* The duration, where a poster would otherwise say nothing about length. */}
      {isVideo && !playing && !failed && duration > 0 && (
        <Text
          variant="caption"
          family="mono"
          className="pointer-events-none absolute bottom-1.5 right-1.5 z-10 rounded-none
                     bg-chrome-scrim/80 px-1.5 py-0.5 text-chrome-ink"
        >
          {formatDuration(duration)}
        </Text>
      )}

      {showChrome && !failed && (
        <div
          className={`pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start
                      justify-between gap-2 bg-gradient-to-b from-chrome-scrim/80 to-transparent
                      p-2 pb-10 ${isFullscreen ? FULLSCREEN_TOP : ""}`}
        >
          <div className="pointer-events-auto flex min-w-0 items-center gap-1">{actions}</div>

          <div className="pointer-events-auto flex shrink-0 items-center gap-1">
            {/*
              Sound is the leftmost control and Close the rightmost, deliberately:
              a mis-tap on the button you reach for mid-clip should not be the one
              that ends the clip.
            */}
            {isVideo && playing && (
              <IconButton
                label={playback.muted ? "Unmute (m)" : "Mute (m)"}
                size="sm"
                onClick={playback.toggleMuted}
                className={CHROME_BUTTON}
              >
                {playback.muted ? <SoundOffIcon /> : <SoundOnIcon />}
              </IconButton>
            )}

            {/*
              Absent rather than broken where it cannot work. iOS Safari refuses
              `requestFullscreen` on anything but a <video>; `useFullscreen`
              catches the rejection and reports `supported: false`, and the right
              outcome is a button that was never offered.
            */}
            {supported && (
              <IconButton
                label={isFullscreen ? "Exit fullscreen (f)" : "Fullscreen (f)"}
                size="sm"
                onClick={() => void toggle()}
                className={CHROME_BUTTON}
              >
                {isFullscreen ? <FullscreenExitIcon /> : <FullscreenEnterIcon />}
              </IconButton>
            )}

            {(playing || onClose) && (
              <IconButton
                label={playing ? `Close ${name}` : "Close"}
                size="sm"
                onClick={close}
                className={CHROME_BUTTON}
              >
                <CloseIcon />
              </IconButton>
            )}
          </div>
        </div>
      )}

      {isVideo && playing && !failed && (
        <div
          className={`pointer-events-none absolute inset-x-0 bottom-0 z-20 flex flex-col gap-1
                      bg-gradient-to-t from-chrome-scrim/85 to-transparent px-3 pb-3 pt-12
                      ${isFullscreen ? FULLSCREEN_BOTTOM : ""}`}
        >
          {playback.blocked && (
            <Text variant="caption" className="pointer-events-auto text-chrome-ink">
              Your browser blocked sound. Press play, then unmute above.
            </Text>
          )}
          <div className="pointer-events-auto mx-auto w-full max-w-2xl">
            <PlayerTransport playback={playback} buffered={buffered} size="sm" />
          </div>
        </div>
      )}

      {overlay}
    </div>
  );
}
