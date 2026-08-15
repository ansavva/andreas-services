import { useCallback, useEffect, useRef, useState } from "react";

import { Spinner, Text } from "@ansavva/design-system";

import { useFullscreen } from "../../hooks/useFullscreen";
import { useKeyboardNav } from "../../hooks/useKeyboardNav";
import type { FileEntry } from "../../types";
import { MediaSurface } from "./MediaSurface";
import { ViewerChrome } from "./ViewerChrome";

interface Props {
  items: FileEntry[];
  loading: boolean;
  exhausted: boolean;
  startIndex: number;
  onLoadMore: () => void;
  onClose: () => void;
}

/** Mount this many panes either side of the snapped one. */
const WINDOW = 2;
/** Start fetching the next page this many panes from the end. */
const PREFETCH_MARGIN = 4;

/**
 * A vertical scroll-snap column, one item per viewport.
 *
 * The snapping itself is CSS (`.reel-scroller` / `.reel-pane` in app.css) —
 * doing it in JS fights the browser's own momentum and never feels right on
 * touch. All this component owns is which pane is current, which is what drives
 * playback: exactly one video plays at a time, and it is the one you are
 * looking at.
 */
export function ReelView({
  items,
  loading,
  exhausted,
  startIndex,
  onLoadMore,
  onClose,
}: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRefs = useRef(new Map<string, HTMLVideoElement>());

  const [current, setCurrent] = useState(startIndex);
  const [muted, setMuted] = useState(true);
  const hasJumped = useRef(false);

  const { isFullscreen, supported, toggle } = useFullscreen(containerRef);

  // Open on the item that was clicked rather than at the top. Runs once, and
  // only after the pane exists — `startIndex` may be past the first page.
  useEffect(() => {
    if (hasJumped.current || startIndex === 0) return;
    const scroller = scrollerRef.current;
    const pane = scroller?.children[startIndex] as HTMLElement | undefined;
    if (!scroller || !pane) return;

    scroller.scrollTo({ top: pane.offsetTop, behavior: "auto" });
    hasJumped.current = true;
  }, [items.length, startIndex]);

  // One observer over every pane. The most-visible pane wins, which is what
  // makes a half-scrolled position resolve to exactly one "current".
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

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
      { root: scroller, threshold: [0.25, 0.5, 0.75, 1] },
    );

    for (const pane of Array.from(scroller.children)) observer.observe(pane);
    return () => observer.disconnect();
  }, [items.length]);

  // Exactly one video plays: the current one. Everything else is paused and
  // rewound, so scrolling back to a clip restarts it instead of resuming
  // halfway through.
  useEffect(() => {
    for (const [key, video] of videoRefs.current) {
      const isCurrent = items[current]?.key === key;
      if (isCurrent) {
        video.muted = muted;
        void video.play().catch(() => {
          /* autoplay refused — the user can tap the pane */
        });
      } else {
        video.pause();
        video.currentTime = 0;
      }
    }
  }, [current, items, muted]);

  useEffect(() => {
    if (!exhausted && current >= items.length - PREFETCH_MARGIN) onLoadMore();
  }, [current, exhausted, items.length, onLoadMore]);

  const step = useCallback(
    (delta: number) => {
      const scroller = scrollerRef.current;
      const target = scroller?.children[current + delta] as HTMLElement | undefined;
      if (!scroller || !target) return;
      scroller.scrollTo({ top: target.offsetTop, behavior: "smooth" });
    },
    [current],
  );

  const toggleMuted = useCallback(() => setMuted((value) => !value), []);

  useKeyboardNav({
    onPrev: () => step(-1),
    onNext: () => step(1),
    onClose,
    onToggleFullscreen: () => void toggle(),
    onTogglePlay: toggleMuted,
  });

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  const currentItem = items[current];

  if (items.length === 0) {
    return (
      <div ref={containerRef} className="fixed inset-0 z-50 flex items-center justify-center bg-black">
        {loading ? (
          <Spinner size="lg" label="Loading media" />
        ) : (
          <div className="flex flex-col items-center gap-4 p-6 text-center">
            <Text variant="body" className="text-white/80">
              No images or videos beneath this folder.
            </Text>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md bg-white/15 px-4 py-2 font-body text-sm text-white hover:bg-white/25"
            >
              Back
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div ref={containerRef} className="fixed inset-0 z-50 bg-black" aria-label="Reel">
      {currentItem && (
        <ViewerChrome
          file={currentItem}
          position={`${current + 1}${exhausted ? ` of ${items.length}` : ""}`}
          isFullscreen={isFullscreen}
          fullscreenSupported={supported}
          onToggleFullscreen={() => void toggle()}
          onClose={onClose}
        />
      )}

      <div ref={scrollerRef} className="reel-scroller no-scrollbar h-full w-full overflow-y-auto">
        {items.map((item, index) => {
          const near = Math.abs(index - current) <= WINDOW;
          return (
            <div
              key={item.key}
              data-index={index}
              className="reel-pane relative flex h-full w-full items-center justify-center"
            >
              {near ? (
                <MediaSurface
                  file={item}
                  variant="reel"
                  active={index === current}
                  muted={muted}
                  onVideoRef={(element) => {
                    if (element) videoRefs.current.set(item.key, element);
                    else videoRefs.current.delete(item.key);
                  }}
                />
              ) : (
                // Outside the window the pane keeps its height (so scroll
                // position and snapping stay honest) but mounts nothing —
                // a hundred <video> elements would exhaust the decoder.
                <div className="h-full w-full" />
              )}
            </div>
          );
        })}
      </div>

      {currentItem?.kind === "video" && (
        <button
          type="button"
          onClick={toggleMuted}
          aria-label={muted ? "Unmute" : "Mute"}
          className="absolute bottom-6 right-4 z-10 rounded-full bg-black/55 p-3 text-white/85
                     transition-colors hover:bg-black/75 hover:text-white
                     focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5 fill-none stroke-current stroke-[1.5]">
            <path d="M11 5 6 9H3v6h3l5 4Z" />
            {muted ? <path d="m16 9 5 6m0-6-5 6" /> : <path d="M15.5 8.5a5 5 0 0 1 0 7M18 6a9 9 0 0 1 0 12" />}
          </svg>
        </button>
      )}

      {loading && (
        <div className="absolute bottom-6 left-1/2 z-10 -translate-x-1/2">
          <Spinner size="sm" label="Loading more" />
        </div>
      )}
    </div>
  );
}
