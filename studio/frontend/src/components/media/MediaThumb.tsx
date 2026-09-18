import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";

import type { AttachRef } from "../../context/CreateBarContext";
import type { Poster } from "../../types";
import { objectRef, startNodeDrag } from "../create/dragRef";
import { useNearViewport } from "../../hooks/useNearViewport";
import { useSignedSrc } from "../../hooks/useSignedSrc";
import { formatDuration } from "../../utils/format";

/**
 * Every class here is a whole literal, and that is not stylistic.
 *
 * Tailwind finds classes by scanning source text, so `object-${fit}` produces
 * nothing at all — the utility is never generated and the media renders
 * unstyled. Anything that varies has to be spelled out somewhere the scanner
 * can read it.
 */
const ASPECTS = {
  square: "aspect-square",
  portrait: "aspect-[3/4]",
  video: "aspect-video",
  /** No ratio of its own — the caller sized the box. */
  auto: "",
} as const;

const FITS = { cover: "object-cover", contain: "object-contain" } as const;

interface Props {
  /**
   * The node id, which is what a re-sign addresses.
   *
   * Not optional and not the key: `/api/asset` signs by node, and a name path
   * would leave every expired tile broken for anything uploaded through the
   * app.
   */
  nodeId: string;
  /**
   * The presigned URL, or nothing at all.
   *
   * **Absent is a real answer, not a caller's mistake.** A record may point at a
   * node the catalog no longer holds — a deleted send, an output whose file went
   * — and the API reports that pointer as the bare `{node}` it honestly is, with
   * no `name` and no `url`. Every tile below the API therefore has to be able to
   * draw "there is nothing here", which is the `Unavailable` state a dead
   * signature already reaches through `onError`.
   *
   * It was typed `string` and the runtime disagreed: a project holding one run
   * with a deleted send crashed the whole feed in `looksLikeVideo` —
   * `new URL(undefined)` throws, and the fallback did `undefined.split("?")`.
   */
  url: string | null | undefined;
  /**
   * What the file is called — used for the hover caption and nothing else.
   *
   * **Not the alt text.** See the `<img>` below: these are decorative inside
   * controls that already carry the name.
   *
   * Optional for the same reason `url` is: a pointer at a node that is gone
   * carries no name either.
   */
  name?: string;
  /**
   * Whether this is a video, when the caller knows.
   *
   * **Omitting it does not mean "image".** A `false` default would make every
   * caller that cannot know — `HeroImage` is `{node, url}` and carries no
   * kind, which is `EntityCard`, `EntityRow` and the project's input pool —
   * silently render an `.mp4` through `<img>` and draw a broken image.
   *
   * Left undefined, the kind is read off the object's extension instead. An
   * explicit value always wins, because a caller with a real `kind` field knows
   * better than a file name does.
   */
  isVideo?: boolean;
  aspect?: keyof typeof ASPECTS;
  /**
   * An exact shape as a CSS `aspect-ratio` value (`"9 / 16"`), which beats
   * `aspect`. The feed passes the plan's own `aspect_ratio` so a portrait clip
   * is not cropped into a landscape box.
   */
  ratio?: string;
  /** `cover` fills the box and crops; `contain` shows the whole frame. */
  fit?: "cover" | "contain";
  /** Bottom-right overlay. A video's duration fills this when nothing else does. */
  badge?: ReactNode;
  /** The name, revealed on hover and focus. Off where a caption sits below the tile. */
  showName?: boolean;
  /** Selected tiles fade so the ring around them reads. */
  dimmed?: boolean;
  /** Extra classes for the media element — the checkerboard, mostly. */
  mediaClassName?: string;
  /** Extra classes for the box: rounding and borders, which vary by surface. */
  className?: string;
  /**
   * A tooltip on the box.
   *
   * Only for the surfaces where nothing else names the picture — an unattached
   * reference sits in a bare grid with no caption and no labelled button, so
   * without this it cannot be identified at all. Leave it off wherever the
   * wrapping control already carries a `title`, or hovering the image overrides
   * that one with a second tooltip saying the same thing.
   */
  title?: string;
  /**
   * What a drag of this picture carries to the create sheet — see `dragRef`.
   *
   * **On by default for a still, and never on for a clip**: every role a tile
   * stands for is a picture. `true` (the default) drags the node as an object;
   * an `AttachRef` drags that instead — a run's output tile passes
   * `refOfOutput` so the sheet records where the picture came from. `false`
   * for the one place a drag would mean something else.
   */
  drag?: boolean | AttachRef;
  /**
   * A clip plays on its own while it is on screen, rather than on hover.
   *
   * **The wall's exception to the rule below.** The hover preview exists
   * because a folder of sixty clips cannot afford sixty decoders; the runs
   * tiles view asks for exactly that look — every clip moving — and pays for
   * it by playing only what is IN the viewport: a second observer, with no
   * margin, starts a clip as it scrolls on and pauses it as it scrolls off,
   * so the decoders live are the screenful you can see, not the page. Off
   * everywhere else. Reduced motion turns it back into a poster.
   */
  autoplay?: boolean;
  /**
   * The small still the render worker made for this file — off a clip's
   * first frame, or a picture scaled down to 640 across — and, for a clip,
   * its length. **With a poster the tile loads nothing else.**
   *
   * For a clip: without one, a tile draws its own poster off the clip's
   * metadata — `preload="metadata"` — and in Chrome that reads the clip
   * nearly whole: measured at ~6 MB per tile, ~290 MB for a wall of
   * forty-eight, and every other request on the page queued behind it. With
   * one, the still is drawn as an `<img>` under the `<video>`, the video is
   * `preload="none"` and costs nothing until a hover or an autoplay slot
   * calls `play()`, and the badge reads `duration` off the record instead
   * of the metadata it no longer loads.
   *
   * For a still: without one, a tile draws the original — a 0.4 MB JPEG for
   * a run's output, 2–8 MB for an uploaded PNG or a phone photo — at 80 CSS
   * pixels across. A feed of twenty runs was a hundred megabytes of
   * thumbnails, arriving six at a time over HTTP/1.1 to S3. The poster is
   * 30–80 KB. The original is still what the viewer opens and what a drag
   * carries: this is a picture of the file, not the file.
   *
   * A poster whose signature has died re-signs like any other picture; one
   * that is gone for good falls back to the file itself — the clip's
   * metadata, the still's original — so the tile is never blank.
   */
  poster?: Poster | null;
  duration?: number | null;
}

/**
 * One image or video, at whatever size the box it is given implies.
 *
 * **This is the only place media is drawn.** There were eight: the browser's
 * tile, a reference tile, a scene's cut row, a run's output tile, a
 * project row's thumb, a movie's scene row, the entity card's hero and the
 * unattached grid — three aspect ratios, three hover behaviours, and one shared
 * bug. Only two of them re-signed an expired URL, so a tab left open past the
 * presign TTL showed broken images on the other six with no way back.
 * `useSignedSrc` is unconditional here.
 *
 * Two loading decisions, and they are the whole of what this rework can do
 * about weight without derivatives:
 *
 * * **Images are `loading="lazy"`.** One tile had this and seven did not, so a
 *   scene page or a run page fetched every full-size frame on mount.
 * * **A video has no `src` until it is near the viewport.** `preload="metadata"`
 *   is how a tile gets a free poster frame out of a bucket that ships no
 *   derivatives, and it is also sixty simultaneous range requests on a folder of
 *   sixty clips. Mounting the source late keeps the poster and drops the stampede
 *   — and because the observer fires immediately for anything already on screen,
 *   nothing visible waits for it.
 *
 * **A video tile previews on hover, and it is deliberately not Replicate's
 * version of that.** Replicate's gallery tiles are bare
 * `<video autoplay muted loop role="presentation">` — they play the moment they
 * are mounted. Studio cannot: a folder here holds sixty clips, and a hundred
 * live decoders is the budget failure `WEB_APP.md` already records against the
 * reel. So the element is the same bare, controlless, muted, looping one and
 * only the *trigger* differs — a mouse entering the box, over a `src` the
 * viewport discipline above has already allowed. Nothing loads earlier than it
 * did; `preload="metadata"` still buys the poster and `near` still gates the
 * source, so a hover on a tile that has not reached the viewport plays nothing
 * rather than starting a fetch.
 *
 * Mouse only, and reduced motion opts out. `pointerType` is checked because a
 * tap emits a synthetic pointer-enter, and on touch the press is already a
 * navigation — a clip that starts playing under the finger that is opening it
 * is a decoder spent on a frame nobody sees.
 *
 * **Presentational only, and it renders no `<button>`.** Every tile in this app
 * is already inside one, and a button cannot contain a button — the constraint
 * that shaped `MediaTile`'s checkbox and `EntityCard`. Callers own the click.
 */
/**
 * The extensions the media tree actually stores video under.
 *
 * Read off the object's own name or its S3 key, never the presigned URL's query
 * string — the signature carries `X-Amz-*` parameters and a naive `.endsWith`
 * against the whole URL never matches.
 */
/**
 * How many clips may play on their own at once, page-wide.
 *
 * Every playing `<video>` is a decoder and a compositor layer at the clip's
 * source size — 720p to 1080p here, since the bucket ships no derivatives —
 * and a wall at 1440px puts fifteen to twenty clips on screen. Measured on
 * the runs wall: the UI dragged the moment a screenful was moving. Eight is
 * enough that the wall reads as moving and few enough that the page keeps
 * up; it is one number, so it is a knob.
 *
 * The queue is what makes the cap fair rather than first-come: a clip that
 * is on screen and denied waits, and the moment a playing clip scrolls off
 * (or unmounts) the first waiting one takes its slot. Everything in it is a
 * closure over the element, so an unmounted tile's cleanup removes itself
 * from both sets and nothing here outlives its tile.
 */
export const AUTOPLAY_BUDGET = 8;
const playing = new Set<HTMLVideoElement>();
const waiting = new Set<() => void>();

function releaseSlot(element: HTMLVideoElement) {
  if (!playing.delete(element)) return;
  const next = waiting.values().next().value;
  if (next) next();
}

const VIDEO_EXTENSIONS = /\.(mp4|mov|webm|m4v)$/i;

function looksLikeVideo(name: string, url: string | null | undefined): boolean {
  if (VIDEO_EXTENSIONS.test(name)) return true;
  // Nothing to read a kind off. The tile draws `Unavailable` either way.
  if (!url) return false;
  try {
    return VIDEO_EXTENSIONS.test(new URL(url).pathname);
  } catch {
    // A relative or malformed URL — the stub suite serves some. Fall back to
    // the raw string with any query cut off by hand.
    return VIDEO_EXTENSIONS.test(url.split("?")[0] ?? "");
  }
}

export function MediaThumb({
  nodeId,
  url,
  name = "",
  isVideo: isVideoProp,
  aspect = "square",
  ratio,
  fit = "cover",
  badge,
  showName = false,
  dimmed = false,
  mediaClassName = "",
  className = "",
  title,
  drag = true,
  autoplay = false,
  poster = null,
  duration: knownDuration = null,
}: Props) {
  const isVideo = isVideoProp ?? looksLikeVideo(name, url);
  const { src, failed, onError } = useSignedSrc(nodeId, url);
  // The still, re-signed on its own node. `still.failed` is also `true` when
  // there is no poster at all, which is the one "fall back to the file" flag.
  const still = useSignedSrc(poster?.node ?? "", poster?.url);
  const hasPoster = !still.failed;

  /**
   * What the `<img>` is showing — the poster while there is one, the
   * original once there is not — and whether it has arrived.
   *
   * **A tile says it is loading.** It used to be the box's plain fill until
   * the picture popped in, which on a slow connection reads as nothing
   * happening; a feed of thumbnails filling one at a time over a minute had
   * no sign that any were on their way. The box shimmers — the same sweep a
   * run in flight draws — until the picture's `load` fires, then the picture
   * fades over it. `loaded` resets whenever the source changes, so a re-sign
   * or a fallback shimmers again rather than showing the old frame's box as
   * done.
   */
  const shown = isVideo ? (hasPoster ? still.src : undefined) : hasPoster ? still.src : src;
  const [loaded, setLoaded] = useState(false);
  const picture = useRef<HTMLImageElement>(null);
  useEffect(() => {
    setLoaded(false);
    // A picture the browser already holds can complete before the listener
    // is on; `complete` with a size is the load event this would have missed.
    const element = picture.current;
    if (element && element.complete && element.naturalWidth > 0) setLoaded(true);
  }, [shown]);
  const onPictureError = useCallback(() => {
    // The poster first: one re-sign, then the file itself. A poster that is
    // gone leaves `still.failed`, `shown` becomes the original, and an error
    // on THAT re-signs the original. (A clip with no poster draws no `<img>`,
    // so the second branch is only ever a still.)
    if (hasPoster) still.onError();
    else onError();
  }, [hasPoster, onError, still]);
  const loading = !failed && shown !== undefined && !loaded;

  /**
   * The drag starts on this box, not on the `<img>` inside it.
   *
   * A browser drags an image by default, carrying its URL — which is not a
   * node and which the sheet refuses. The `<img>` is told not to, so the box
   * is the innermost draggable thing under the pointer and the payload is
   * ours; the picture still follows the cursor as the drag image, because
   * the browser takes the dragged element's own pixels for that.
   */
  const draggable = drag !== false && !isVideo && !failed;
  const onDragStart = (event: DragEvent) =>
    startNodeDrag(event, drag === true ? objectRef(nodeId, url, name) : (drag as AttachRef));

  const [duration, setDuration] = useState<number | null>(knownDuration);
  const box = useRef<HTMLSpanElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const near = useNearViewport(box, isVideo);

  /**
   * Start or stop the hover preview.
   *
   * The `element.src` guard is the viewport discipline showing through: with no
   * source mounted there is nothing to play, and calling `play()` anyway is how
   * a hover would turn into the very range request `near` exists to defer.
   *
   * A rejected `play()` is ordinary rather than exceptional here — leaving the
   * box before the promise settles aborts it — so it is swallowed. This is not
   * the reel's `NotAllowedError` case: the element is muted, which is the
   * condition every autoplay policy grants.
   */
  const preview = useCallback((on: boolean) => {
    const element = video.current;
    if (!element || !element.src) return;
    // Under `autoplay` the viewport decides, and a leave must not pause a
    // clip that is still on screen.
    if (autoplay) return;
    if (on) {
      if (prefersReducedMotion()) return;
      void element.play().catch(() => undefined);
    } else {
      element.pause();
      element.currentTime = 0;
    }
  }, [autoplay]);

  /**
   * Play while on screen, pause when off it — see `autoplay` on the props.
   *
   * `src` is a dependency on purpose. A feed page re-read — a refetch on
   * focus, a row patched by `useRunWatch` — carries a FRESH presigned URL for
   * the same output, and a `<video>` whose `src` changes reloads and stops.
   * Re-arming on `src` asks the observer again, and it answers with the
   * tile's current visibility, so the clip resumes where the wall is and
   * stays paused where it is not.
   *
   * **Bounded by `AUTOPLAY_BUDGET`.** On screen is necessary, not
   * sufficient: a clip past the cap holds its poster in `waiting` and starts
   * when a playing one leaves. See the budget's note for why eight.
   *
   * **The tab coming back is asked for too.** Chrome pauses a muted, video-
   * only element the moment the tab is hidden ("paused to save power") and
   * never resumes it, so a wall left for another tab came back still — every
   * clip on its frame. `visibilitychange` re-runs the same decision the
   * observer made, off what it last said.
   *
   * jsdom has no `IntersectionObserver`, in which case the clip plays
   * outright, which is what a test that turns this on expects.
   */
  useEffect(() => {
    if (!autoplay || !isVideo || !near || failed || !src) return;
    const element = video.current;
    if (!element || prefersReducedMotion()) return;
    const play = () => void element.play().catch(() => undefined);
    if (typeof IntersectionObserver === "undefined") {
      play();
      return () => element.pause();
    }
    let onScreen = false;
    const sync = () => {
      if (!onScreen) {
        waiting.delete(sync);
        element.pause();
        releaseSlot(element);
      } else if (playing.has(element) || playing.size < AUTOPLAY_BUDGET) {
        waiting.delete(sync);
        playing.add(element);
        play();
      } else {
        // On screen but over budget: hold the poster and wait for a slot.
        waiting.add(sync);
        element.pause();
      }
    };
    const observer = new IntersectionObserver((entries) => {
      onScreen = entries.some((entry) => entry.isIntersecting);
      sync();
    });
    observer.observe(element);
    const onVisible = () => {
      if (!document.hidden) sync();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisible);
      waiting.delete(sync);
      element.pause();
      releaseSlot(element);
    };
  }, [autoplay, failed, isVideo, near, src]);

  const media = `h-full w-full ${FITS[fit]} ${dimmed ? "opacity-75" : ""} ${mediaClassName}`;
  // Over the shimmer once it has arrived. `opacity-75` for a dimmed tile is
  // on `media`; this one only hides a picture that is not there yet.
  const fade = `transition-opacity duration-300 ${loaded ? "" : "opacity-0"}`;

  return (
    <span
      ref={box}
      title={title}
      onPointerEnter={(event) => {
        if (isVideo && event.pointerType === "mouse") preview(true);
      }}
      onPointerLeave={(event) => {
        if (isVideo && event.pointerType === "mouse") preview(false);
      }}
      draggable={draggable || undefined}
      onDragStart={draggable ? onDragStart : undefined}
      className={`relative block overflow-hidden bg-surface-alt ${loading ? "studio-shimmer" : ""} ${ratio ? "" : ASPECTS[aspect]} ${className}`}
      data-loading={loading || undefined}
      style={ratio ? { aspectRatio: ratio } : undefined}
    >
      {failed ? (
        <span className="flex h-full w-full items-center justify-center px-2 text-center text-xs text-muted">
          Unavailable
        </span>
      ) : isVideo ? (
        <>
          {/* The still under the clip: what the tile shows until the clip
              plays, at which point the video's frames draw over it. */}
          {hasPoster && (
            <img
              ref={picture}
              src={shown}
              alt=""
              onLoad={() => setLoaded(true)}
              onError={onPictureError}
              loading="lazy"
              decoding="async"
              draggable={false}
              data-testid="poster"
              className={`absolute inset-0 ${media} ${fade}`}
            />
          )}
          <video
            ref={video}
            // `src` withheld until near the viewport — see the note above. `key`
            // is not needed: setting src on a mounted <video> starts the load.
            src={near ? src : undefined}
            onError={onError}
            onLoadedMetadata={(event) =>
              setDuration(event.currentTarget.duration)
            }
            // With a still to draw, nothing is loaded until `play()` — see
            // `poster` on the props for what `metadata` costs.
            preload={hasPoster ? "none" : "metadata"}
            // No `controls`, and `role="presentation"` for the same reason the
            // `<img>` below carries an empty `alt`: this is a picture inside a
            // control that already has a name, not a player.
            role="presentation"
            muted
            loop
            playsInline
            className={`relative ${media}`}
          />
        </>
      ) : (
        <img
          ref={picture}
          src={shown}
          onLoad={() => setLoaded(true)}
          data-testid={hasPoster ? "poster" : undefined}
          // **Decorative, deliberately.** Every one of these sits inside a
          // control that is already labelled — a button with the file's name as
          // its `title`, a row that spells it out beside the picture. An `alt`
          // here does not add information, it *replaces* the label: a button's
          // accessible name comes from its contents before its title, so the
          // filename would win over the prompt a tile is captioned
          // with. Empty alt keeps the thumbnail out of the name and leaves it
          // `role="presentation"`, which is what it is.
          alt=""
          onError={onPictureError}
          loading="lazy"
          decoding="async"
          draggable={false}
          className={`${media} ${fade}`}
        />
      )}

      {/* Square, and mono: a duration is metadata. `bg-overlay-scrim/80` is the
          media-chrome scrim at the weight the black literal here used to
          carry — a badge over media has to be dark, and the point of the token
          is that "dark, over a frame" is one thing this app can re-value. */}
      {(badge ?? (isVideo && !failed)) && (
        <span
          className="pointer-events-none absolute bottom-1.5 right-1.5 bg-overlay-scrim/80 px-1.5
                     py-0.5 font-mono text-[11px] tabular-nums text-overlay-ink"
        >
          {badge ?? (duration ? formatDuration(duration) : "video")}
        </span>
      )}

      {showName && (
        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-gradient-to-t
                     from-overlay-scrim/85 to-transparent px-2 pb-1.5 pt-6 text-left font-mono text-[11px]
                     text-overlay-ink
                     opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
        >
          {name}
        </span>
      )}
    </span>
  );
}

/**
 * Whether the reader has asked for less motion.
 *
 * Read at the moment of the hover rather than subscribed to: this decides one
 * `play()` call, and a `matchMedia` listener per tile would be sixty listeners
 * on a folder of sixty clips to answer a question that costs nothing to ask.
 *
 * The `typeof` guard is for jsdom, which implements no `matchMedia` at all —
 * a test that renders a grid should not have to stub one.
 */
function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function")
    return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
