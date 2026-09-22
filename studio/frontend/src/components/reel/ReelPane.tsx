import { useCallback, useEffect, useRef, useState } from "react";

import { useSignedSrc } from "../../hooks/useSignedSrc";
import type { FileEntry } from "../../types";
import { HeartFilledIcon, PlayIcon } from "../common/icons";
import { Unavailable } from "../media/playerShell";
import { useTaps } from "./useTaps";

interface Props {
  file: FileEntry;
  /** The snapped pane: its clip plays, and only its clip. */
  active: boolean;
  muted: boolean;
  /** The clip's element, for the reel's mute press and Space — `null` on the way out. */
  onVideoRef: (id: string, element: HTMLVideoElement | null) => void;
  /** A double tap — the reel answers with the heart. */
  onHeart: () => void;
}

/** How long the burst is on screen; matches `studio-heart-burst` in app.css. */
const BURST_MS = 700;

/**
 * One item of the reel: a clip or a still, filling the viewport, and the two
 * gestures the reel takes on the picture itself.
 *
 * **A bare `<video>`, not `ClipPlayer`.** The Video.js skin is the player
 * every page draws a clip on, and it stays exactly as shipped there — but its
 * surface is a transport: a seek bar, a volume, a settings menu, and its own
 * tap and double-tap gestures (seek, fullscreen). A reel is the opposite
 * kind of surface: the picture, edge to edge, and a finger that means
 * *pause* once and *heart* twice. Those two cannot both own the same tap,
 * so the reel plays its clips itself — muted autoplay, `loop`,
 * `playsInline` — and draws nothing over them but a paused mark and a
 * progress line.
 *
 * **The element is the source of truth for paused.** Space in the reel and
 * a tap here both act on the element; the mark follows its `play`/`pause`
 * events, so the two never disagree about what is on screen.
 *
 * **Mute is set on the element, not only as a prop.** React's `muted` is a
 * property set once at mount, and `useSignedSrc` can swap `src` under a
 * live element; setting it in an effect on every change is what keeps a
 * clip that arrives after the unmute press arriving with sound.
 */
export function ReelPane({ file, active, muted, onVideoRef, onHeart }: Props) {
  const isVideo = file.kind === "video";
  const { src, failed, onError } = useSignedSrc(file.id, file.url);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const paneRef = useRef<HTMLDivElement | null>(null);

  const [paused, setPaused] = useState(false);
  const [progress, setProgress] = useState(0);
  const [burst, setBurst] = useState<{ x: number; y: number; key: number } | null>(null);

  const setVideo = useCallback(
    (element: HTMLVideoElement | null) => {
      videoRef.current = element;
      if (element) element.muted = muted;
      onVideoRef(file.id, element);
    },
    // `muted` is deliberately not a dependency: the ref callback must not
    // re-run on every press, and the effect below carries the changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [file.id, onVideoRef],
  );

  useEffect(() => {
    const video = videoRef.current;
    if (video) video.muted = muted;
  }, [muted]);

  /**
   * The snapped clip plays; a clip scrolled away stops and rewinds, so
   * coming back to it is its start rather than wherever the eye left it.
   *
   * A refused `play()` is the autoplay policy: sound without a gesture. The
   * fallback is to play muted rather than to stop — a silent reel is a reel;
   * a still frame with a spinner is not.
   */
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !isVideo) return;
    if (!active) {
      video.pause();
      video.currentTime = 0;
      return;
    }
    const attempt = video.play();
    if (attempt) {
      attempt.catch(() => {
        video.muted = true;
        void video.play()?.catch(() => undefined);
      });
    }
  }, [active, isVideo, src]);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play()?.catch(() => undefined);
    else video.pause();
  }, []);

  const heart = useCallback(
    (at: { x: number; y: number }) => {
      // The tap is in viewport coordinates; the burst is placed in the pane's.
      const box = paneRef.current?.getBoundingClientRect();
      setBurst({ x: at.x - (box?.left ?? 0), y: at.y - (box?.top ?? 0), key: Date.now() });
      onHeart();
    },
    [onHeart],
  );

  useEffect(() => {
    if (!burst) return;
    const timer = setTimeout(() => setBurst(null), BURST_MS);
    return () => clearTimeout(timer);
  }, [burst]);

  const taps = useTaps({
    onTap: isVideo ? togglePlay : undefined,
    onDoubleTap: heart,
  });

  return (
    <div
      ref={paneRef}
      className="relative flex h-full w-full touch-pan-y select-none items-center justify-center"
      data-testid="reel-pane"
      {...taps}
    >
      {failed ? (
        <Unavailable />
      ) : isVideo ? (
        <video
          ref={setVideo}
          src={src}
          poster={file.poster?.url ?? undefined}
          className="h-full w-full object-contain"
          loop
          playsInline
          preload="auto"
          onError={onError}
          onPlay={() => setPaused(false)}
          onPause={() => setPaused(true)}
          onTimeUpdate={(event) => {
            const { currentTime, duration } = event.currentTarget;
            setProgress(duration > 0 ? currentTime / duration : 0);
          }}
        />
      ) : (
        <img
          src={src}
          alt={file.name}
          className="h-full w-full object-contain"
          draggable={false}
          onError={onError}
        />
      )}

      {/* The paused mark: the picture stays, the reel says it has stopped. */}
      {isVideo && active && paused && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
        >
          <PlayIcon className="size-16 fill-white/80 stroke-none drop-shadow" />
        </div>
      )}

      {/* Where the clip is, as a hairline along the foot of the pane —
          under the chrome's safe-area padding, which is what keeps it off a
          home indicator. */}
      {isVideo && active && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-[max(0.25rem,env(safe-area-inset-bottom))] h-0.5 bg-white/20"
        >
          <div className="h-full bg-white/80" style={{ width: `${progress * 100}%` }} />
        </div>
      )}

      {/* The heart a double tap leaves, where the finger went down. Keyed
          per press so a second double tap restarts the swell. Two spans:
          the outer centres on the point, the inner animates — the keyframe
          sets `transform`, which would replace the translate. */}
      {burst && (
        <span
          key={burst.key}
          aria-hidden="true"
          data-testid="heart-burst"
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
          style={{ left: burst.x, top: burst.y }}
        >
          <span className="studio-heart-burst block">
            <HeartFilledIcon className="size-24 fill-white stroke-none drop-shadow-lg" />
          </span>
        </span>
      )}
    </div>
  );
}
