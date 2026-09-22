import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { Button, IconButton, Text } from "@ansavva/design-system";

import { useFavorites } from "../../hooks/useFavorites";
import { useKeyboardNav } from "../../hooks/useKeyboardNav";
import { useMedia } from "../../hooks/useMedia";
import { ApertureSpinner } from "../common/Aperture";
import { EmptyState } from "../common/EmptyState";
import { CloseIcon, HeartFilledIcon, SoundOffIcon, SoundOnIcon } from "../common/icons";
import { LoadError } from "../common/LoadError";
import { ReelPane } from "./ReelPane";
import { forgetPosition, recallPosition, rememberPosition } from "./reelPosition";

interface Props {
  projectId: string;
  /** The project's root folder — what the walk is under. */
  rootId: string;
  name: string;
  onClose: () => void;
}

/** Mount media this many panes either side of the snapped one. */
const WINDOW = 2;
/** Ask for the next page this many panes from the end of what is loaded. */
const PREFETCH_MARGIN = 4;

/**
 * A project's reel — `/p/<id>/reel`: everything it holds, oldest first, one
 * item per screen, swiped through.
 *
 * **Back, after being taken out.** Studio had a reel and lost it to the
 * object page, on the argument that opening a tile already scrolled the same
 * walk. What that page is not is a way to *watch* a project: it hangs under
 * the header with a rail beside it, and it opens on the newest thing. A reel
 * is the picture and nothing else, and it runs the other way — a project is
 * a piece of work, and watching it is watching it get made. So this is
 * **oldest to newest**, and it is the one surface in the app that is.
 *
 * **It is a recursive walk of the project's root** — `useMedia`, the same
 * hook the library's Media view pages on — so a run's outputs, a scene's
 * cuts, a movie and the input pool are all in it, in the order they were
 * made, and no row fetches anything.
 *
 * **It remembers where it was left, per project, in this browser**
 * (`reelPosition`): the snapped item's id is written as it changes, read
 * back on open, and the walk pages forward until it finds it. Reaching the
 * end forgets the place, so the next open starts over — and the last pane
 * offers Start over for a person who wants it now.
 *
 * **A double tap hearts.** `useFavorites` — the same set every heart in the
 * app reads — set to true, never toggled: a second double tap on a
 * favorited picture is a person enjoying it, not a person undoing
 * themselves. The heart at the foot of the chrome is the state the press
 * leaves, a mark and not a control, exactly as on a tile.
 *
 * **Which pane is current is the browser's answer, not a counter.** One
 * `IntersectionObserver` over every pane; the most visible wins. The
 * snapping is CSS (`.reel-scroller` / `.reel-pane` in app.css).
 *
 * The overlay covers the whole viewport — header, rail and sheet — because a
 * reel under a header is a page, and the page already exists.
 */
export function ProjectReel({ projectId, rootId, name, onClose }: Props) {
  const { items, exhausted, loading, error, truncated, loadMore, reload } = useMedia(
    rootId,
    "oldest",
    true,
  );
  const favorites = useFavorites();

  const scrollerRef = useRef<HTMLDivElement>(null);
  const videos = useRef(new Map<string, HTMLVideoElement>());

  const [current, setCurrent] = useState(0);
  const [muted, setMuted] = useState(true);
  // Whether the opening scroll — to the remembered item — has been made.
  // Nothing is remembered or prefetched before it, and the column is kept
  // invisible, so the first item is not flashed on the way past.
  const [landed, setLanded] = useState(false);
  const recalled = useRef(recallPosition(projectId));

  const currentItem = items[current];
  const isVideo = currentItem?.kind === "video";
  const atEnd = exhausted && items.length > 0 && current === items.length - 1;

  // Nothing under the reel scrolls while it is up — a swipe past either end
  // would otherwise carry on into the feed it is drawn over.
  useEffect(() => {
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
    };
  }, []);

  /**
   * Open on the remembered item. It may be past the first page, so the walk
   * is paged forward until it turns up; a walk that ends without it — the
   * item was deleted — starts from the top and forgets it.
   */
  useEffect(() => {
    if (landed || loading) return;
    const wanted = recalled.current;
    if (wanted === null) {
      if (items.length > 0 || exhausted) setLanded(true);
      return;
    }
    const index = items.findIndex((item) => item.id === wanted);
    if (index >= 0) {
      const pane = scrollerRef.current?.children[index] as HTMLElement | undefined;
      if (pane) scrollerRef.current?.scrollTo({ top: pane.offsetTop, behavior: "auto" });
      setCurrent(index);
      setLanded(true);
    } else if (exhausted) {
      forgetPosition(projectId);
      setLanded(true);
    } else {
      loadMore();
    }
  }, [exhausted, items, landed, loadMore, loading, projectId]);

  // One observer over every pane. The most-visible pane wins, which is what
  // makes a half-scrolled position resolve to exactly one "current".
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller || !landed) return;

    const observer = new IntersectionObserver(
      (entries) => {
        let best: { index: number; ratio: number } | null = null;
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const index = Number((entry.target as HTMLElement).dataset.index);
          if (!best || entry.intersectionRatio > best.ratio) {
            best = { index, ratio: entry.intersectionRatio };
          }
        }
        if (best) setCurrent(best.index);
      },
      { root: scroller, threshold: [0.5, 0.75, 1] },
    );

    for (const pane of Array.from(scroller.children)) observer.observe(pane);
    return () => observer.disconnect();
  }, [items.length, landed]);

  // The place, kept as it moves — and let go of at the end.
  useEffect(() => {
    if (!landed || !currentItem) return;
    if (atEnd) forgetPosition(projectId);
    else rememberPosition(projectId, currentItem.id);
  }, [atEnd, currentItem, landed, projectId]);

  // The next page, asked for before the last loaded pane is reached.
  useEffect(() => {
    if (!landed || exhausted) return;
    if (current >= items.length - PREFETCH_MARGIN) loadMore();
  }, [current, exhausted, items.length, landed, loadMore]);

  // The column takes the keys — Up/Down, PageDown, Home, End are the
  // browser's own scroll, and snapping makes each a pane.
  useEffect(() => {
    if (landed) scrollerRef.current?.focus();
  }, [landed]);

  /**
   * Sound is set on the element inside the press, and state follows.
   * Safari grants sound only within the gesture's own turn of the event
   * loop; a state change an effect later is not the press.
   */
  const toggleMuted = useCallback(() => {
    const next = !muted;
    const video = currentItem ? videos.current.get(currentItem.id) : undefined;
    if (video) video.muted = next;
    setMuted(next);
  }, [currentItem, muted]);

  const togglePlay = useCallback(() => {
    const video = currentItem ? videos.current.get(currentItem.id) : undefined;
    if (!video) return;
    if (video.paused) void video.play()?.catch(() => undefined);
    else video.pause();
  }, [currentItem]);

  const heart = useCallback(
    (id: string) => favorites.setFavorite(id, true),
    [favorites],
  );

  const startOver = useCallback(() => {
    scrollerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  useKeyboardNav({
    onClose,
    onTogglePlay: isVideo ? togglePlay : undefined,
    onToggleMuted: isVideo ? toggleMuted : undefined,
  });

  // One stable callback for every pane: a fresh arrow per render would
  // detach and re-attach every clip's element on every tick.
  const registerVideo = useCallback((id: string, element: HTMLVideoElement | null) => {
    if (element) videos.current.set(id, element);
    else videos.current.delete(id);
  }, []);

  const chromeButton = "size-4 fill-none stroke-current stroke-[1.5]";

  if (error) {
    return (
      <Shell name={name}>
        <div className="flex h-full items-center justify-center p-6">
          <div className="w-full max-w-md">
            <LoadError
              what="the reel"
              message={error}
              onRetry={reload}
              escape={{ label: "Close", onClick: onClose }}
            />
          </div>
        </div>
      </Shell>
    );
  }

  if (items.length === 0) {
    return (
      <Shell name={name}>
        <div className="flex h-full items-center justify-center p-6 text-center">
          {loading || !exhausted ? (
            <ApertureSpinner size="lg" label="Loading the reel" className="text-white" />
          ) : (
            <EmptyState
              title="No images or videos yet."
              hint="The reel plays what the project has made. Run something, then come back."
              className="items-center text-center"
              action={
                <Button intent="secondary" size="sm" onClick={onClose}>
                  Close
                </Button>
              }
            />
          )}
        </div>
      </Shell>
    );
  }

  return (
    <Shell name={name}>
      {/* The chrome: a scrim at the top, the place and the name on the left,
          sound and close on the right. `env(safe-area-inset-top)` keeps it
          under a notch. */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between
                   gap-3 bg-gradient-to-b from-black/70 to-transparent px-3 pb-10
                   pt-[max(0.75rem,env(safe-area-inset-top))] text-white"
      >
        <div className="flex min-w-0 flex-col gap-0.5">
          <Text variant="caption" family="mono" className="tabular-nums text-white/80">
            {current + 1} of {items.length}
            {exhausted ? (truncated ? "+" : "") : "…"}
          </Text>
          {currentItem && (
            <Text variant="caption" truncate className="text-white/80">
              {currentItem.name}
            </Text>
          )}
        </div>
        <div className="pointer-events-auto flex shrink-0 items-center gap-1">
          {isVideo && (
            <IconButton
              label={muted ? "Unmute (m)" : "Mute (m)"}
              size="sm"
              intent="overlay"
              pressed={!muted}
              onClick={toggleMuted}
              className=""
            >
              {muted ? (
                <SoundOffIcon className={chromeButton} />
              ) : (
                <SoundOnIcon className={chromeButton} />
              )}
            </IconButton>
          )}
          <IconButton label="Close (Esc)" size="sm" intent="overlay" onClick={onClose} className="">
            <CloseIcon className={chromeButton} />
          </IconButton>
        </div>
      </div>

      <div
        ref={scrollerRef}
        tabIndex={-1}
        aria-label={`${name} reel`}
        className={`reel-scroller no-scrollbar relative h-full w-full overflow-y-auto outline-none ${
          landed ? "" : "invisible"
        }`}
      >
        {items.map((item, index) => {
          const near = Math.abs(index - current) <= WINDOW;
          return (
            <div key={item.id} data-index={index} className="reel-pane relative w-full">
              {near ? (
                <ReelPane
                  file={item}
                  active={landed && index === current}
                  muted={muted}
                  onVideoRef={registerVideo}
                  onHeart={() => heart(item.id)}
                />
              ) : (
                // Outside the window the pane keeps its height (so scroll
                // position and snapping stay honest) but mounts nothing — a
                // hundred <video> elements would exhaust the decoder.
                <div className="h-full w-full" />
              )}
            </div>
          );
        })}
      </div>

      {/* The foot: the mark a heart leaves, and — at the end — the way back
          to the start. Above the pane's progress line and clear of a home
          indicator. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-end justify-between
                   gap-3 px-3 pb-[max(1rem,env(safe-area-inset-bottom))] pt-10"
      >
        <div className="flex h-8 items-center">
          {currentItem && favorites.isFavorite(currentItem.id) && (
            <span
              aria-label="Favorited"
              role="img"
              data-testid="reel-favorited"
              className="flex size-8 items-center justify-center rounded-pill bg-black/50"
            >
              <HeartFilledIcon className="size-4 fill-current stroke-none text-danger" />
            </span>
          )}
        </div>
        {atEnd && (
          <Button intent="secondary" size="sm" onClick={startOver} className="pointer-events-auto">
            Start over
          </Button>
        )}
      </div>

      {loading && landed && (
        <div className="pointer-events-none absolute bottom-16 left-1/2 z-10 -translate-x-1/2">
          <ApertureSpinner size="sm" label="Loading more" className="text-white" />
        </div>
      )}
    </Shell>
  );
}

/**
 * The black box over everything. `100dvh` and not `inset-0`: on a phone the
 * two are not the same height once the browser's own toolbar has shown or
 * hidden, and a pane sized to the wrong one leaves a strip of the page
 * beneath showing through.
 */
function Shell({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${name} reel`}
      className="fixed inset-x-0 top-0 z-50 bg-black text-white"
      style={{ height: "100dvh" }}
    >
      {children}
    </div>
  );
}
