import { useEffect, useRef, useState, type ReactNode } from "react";

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
 * **Presentational only, and it renders no `<button>`.** Every tile in this app
 * is already inside one, and a button cannot contain a button — the constraint
 * that shaped `MediaTile`'s checkbox and `EntityCard`. Callers own the click.
 */
export function MediaThumb({
  nodeId,
  url,
  name,
  isVideo = false,
  aspect = "square",
  fit = "cover",
  badge,
  showName = false,
  dimmed = false,
  mediaClassName = "",
  className = "",
  title,
}: Props) {
  const { src, failed, onError } = useSignedSrc(nodeId, url);
  const [duration, setDuration] = useState<number | null>(null);
  const box = useRef<HTMLSpanElement>(null);
  const near = useNearViewport(box, isVideo);

  const media = `h-full w-full ${FITS[fit]} ${dimmed ? "opacity-75" : ""} ${mediaClassName}`;

  return (
    <span
      ref={box}
      title={title}
      className={`relative block overflow-hidden bg-surface-alt ${ASPECTS[aspect]} ${className}`}
    >
      {failed ? (
        <span className="flex h-full w-full items-center justify-center px-2 text-center text-xs text-muted">
          Unavailable
        </span>
      ) : isVideo ? (
        <video
          // `src` withheld until near the viewport — see the note above. `key`
          // is not needed: setting src on a mounted <video> starts the load.
          src={near ? src : undefined}
          onError={onError}
          onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
          preload="metadata"
          muted
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

      {(badge ?? (isVideo && !failed)) && (
        <span
          className="pointer-events-none absolute bottom-1.5 right-1.5 rounded-sm bg-black/70 px-1.5
                     py-0.5 font-body text-[11px] tabular-nums text-white"
        >
          {badge ?? (duration ? formatDuration(duration) : "video")}
        </span>
      )}

      {showName && (
        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80
                     to-transparent px-2 pb-1.5 pt-6 text-left font-body text-[11px] text-white/90
                     opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
        >
          {name}
        </span>
      )}
    </span>
  );
}

/**
 * Whether an element has come within a screen of the viewport.
 *
 * `rootMargin` is a full viewport height so a clip is loading by the time it is
 * scrolled to rather than starting then. Latches on: once something has been
 * seen there is no benefit to unloading it, and a `<video>` whose `src` was
 * taken away goes blank.
 *
 * Returns `true` outright when not watching, so the image path never pays for
 * an observer it does not use.
 */
function useNearViewport(ref: React.RefObject<HTMLElement | null>, watch: boolean): boolean {
  const [near, setNear] = useState(!watch);

  useEffect(() => {
    if (!watch || near) return;
    const element = ref.current;
    if (!element) return;

    // jsdom has no IntersectionObserver, and a test that renders a grid should
    // not have to stub one to see anything.
    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setNear(true);
      },
      { rootMargin: "100% 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [near, ref, watch]);

  return near;
}
