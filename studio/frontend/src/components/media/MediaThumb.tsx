import { useCallback, useRef, useState, type ReactNode } from "react";

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
   * Not optional and not the key: `/api/asset` signs by node, and passing a
   * name path is what left every expired tile broken for anything uploaded
   * through the app (#432).
   */
  nodeId: string;
  url: string;
  /**
   * What the file is called — used for the hover caption and nothing else.
   *
   * **Not the alt text.** See the `<img>` below: these are decorative inside
   * controls that already carry the name.
   */
  name: string;
  /**
   * Whether this is a video, when the caller knows.
   *
   * **Omitting it no longer means "image".** It used to default to `false`, so
   * every caller that could not know — `HeroImage` is `{node, url}` and carries
   * no kind, which is `EntityCard`, `EntityRow` and the project's input pool —
   * silently rendered an `.mp4` through `<img>` and drew a broken image. The
   * runs list did it too, and that is how this was found.
   *
   * Left undefined, the kind is read off the object's extension instead. An
   * explicit value always wins, because a caller with a real `kind` field knows
   * better than a file name does.
   */
  isVideo?: boolean;
  aspect?: keyof typeof ASPECTS;
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
}

/**
 * One image or video, at whatever size the box it is given implies.
 *
 * **This is the only place media is drawn.** There were eight: the browser's
 * tile, a reference tile, the storyboard's frame, a run's output tile, a
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
 *   storyboard or a run page fetched every full-size frame on mount.
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
const VIDEO_EXTENSIONS = /\.(mp4|mov|webm|m4v)$/i;

function looksLikeVideo(name: string, url: string): boolean {
  if (VIDEO_EXTENSIONS.test(name)) return true;
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
  name,
  isVideo: isVideoProp,
  aspect = "square",
  fit = "cover",
  badge,
  showName = false,
  dimmed = false,
  mediaClassName = "",
  className = "",
  title,
}: Props) {
  const isVideo = isVideoProp ?? looksLikeVideo(name, url);

  const { src, failed, onError } = useSignedSrc(nodeId, url);
  const [duration, setDuration] = useState<number | null>(null);
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
    if (on) {
      if (prefersReducedMotion()) return;
      void element.play().catch(() => undefined);
    } else {
      element.pause();
      element.currentTime = 0;
    }
  }, []);

  const media = `h-full w-full ${FITS[fit]} ${dimmed ? "opacity-75" : ""} ${mediaClassName}`;

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
      className={`relative block overflow-hidden bg-surface-alt ${ASPECTS[aspect]} ${className}`}
    >
      {failed ? (
        <span className="flex h-full w-full items-center justify-center px-2 text-center text-xs text-muted">
          Unavailable
        </span>
      ) : isVideo ? (
        <video
          ref={video}
          // `src` withheld until near the viewport — see the note above. `key`
          // is not needed: setting src on a mounted <video> starts the load.
          src={near ? src : undefined}
          onError={onError}
          onLoadedMetadata={(event) =>
            setDuration(event.currentTarget.duration)
          }
          preload="metadata"
          // No `controls`, and `role="presentation"` for the same reason the
          // `<img>` below carries an empty `alt`: this is a picture inside a
          // control that already has a name, not a player.
          role="presentation"
          muted
          loop
          playsInline
          className={media}
        />
      ) : (
        <img
          src={src}
          // **Decorative, deliberately.** Every one of these sits inside a
          // control that is already labelled — a button with the file's name as
          // its `title`, a row that spells it out beside the picture. An `alt`
          // here does not add information, it *replaces* the label: a button's
          // accessible name comes from its contents before its title, so the
          // filename would win over the prompt a storyboard tile is captioned
          // with. Empty alt keeps the thumbnail out of the name and leaves it
          // `role="presentation"`, which is what it is.
          alt=""
          onError={onError}
          loading="lazy"
          decoding="async"
          className={media}
        />
      )}

      {/* Square, and mono: a duration is metadata. `bg-neutral-1/80` is the
          ramp's darkest step at the weight the black literal here used to
          carry — a scrim over media has to be dark, and the point of the ramp
          is that "dark" is now a token this app can re-value. */}
      {(badge ?? (isVideo && !failed)) && (
        <span
          className="pointer-events-none absolute bottom-1.5 right-1.5 bg-neutral-1/80 px-1.5
                     py-0.5 font-mono text-[11px] tabular-nums text-neutral-12"
        >
          {badge ?? (duration ? formatDuration(duration) : "video")}
        </span>
      )}

      {showName && (
        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-gradient-to-t
                     from-neutral-1/85 to-transparent px-2 pb-1.5 pt-6 text-left font-mono text-[11px]
                     text-neutral-12
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
