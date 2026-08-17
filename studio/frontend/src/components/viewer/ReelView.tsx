import { useCallback, useEffect, useRef, useState } from "react";

import { Spinner, Text } from "@ansavva/design-system";

import { useFullscreen } from "../../hooks/useFullscreen";
import { useKeyboardNav } from "../../hooks/useKeyboardNav";
import { useReelPlayback } from "../../hooks/useReelPlayback";
import type { FileEntry } from "../../types";
import { MediaSurface } from "./MediaSurface";
import { VideoScrubber } from "./VideoScrubber";
import { ViewerChrome } from "./ViewerChrome";

interface Props {
  items: FileEntry[];
  loading: boolean;
  exhausted: boolean;
  /** True when the server's recursive walk hit its cap. */
  truncated?: boolean;
  startIndex: number;
  onLoadMore?: () => void;
  onClose: () => void;
  /** Fires as the snapped item changes — this is what drives the URL. */
  onCurrentChange?: (item: FileEntry) => void;
  onRename?: (file: FileEntry, name: string) => Promise<unknown>;
  onDelete?: (file: FileEntry) => Promise<unknown>;
}

/** Mount this many panes either side of the snapped one. */
const WINDOW = 2;
/** Start fetching the next page this many panes from the end. */
const PREFETCH_MARGIN = 4;

/**
 * A vertical scroll-snap column, one item per viewport.
 *
 * **This is the only media viewer in studio.** There used to be a lightbox
 * beside it — a horizontal filmstrip with its own keyboard map, its own swipe
 * handling and its own idea of what "next" meant. Two viewers over the same
 * files is two things to keep in step for no benefit, so the reel absorbed the
 * job: opening a tile opens the reel at that tile.
 *
 * The snapping itself is CSS (`.reel-scroller` / `.reel-pane` in app.css) —
 * doing it in JS fights the browser's own momentum and never feels right on
 * touch. What this component owns is which pane is current; `useReelPlayback`
 * owns everything that follows from that, including the sound.
 */
export function ReelView({
  items,
  loading,
  exhausted,
  truncated = false,
  startIndex,
  onLoadMore,
  onClose,
  onCurrentChange,
  onRename,
  onDelete,
}: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [current, setCurrent] = useState(startIndex);
  const hasJumped = useRef(false);

  const { isFullscreen, supported, toggle } = useFullscreen(containerRef);
  const currentItem = items[current];
  const playback = useReelPlayback(currentItem?.key);

  // Open on the item that was clicked rather than at the top. Runs once, and
  // only after the pane exists — `startIndex` may be past the first page.
  useEffect(() => {
    if (hasJumped.current || startIndex === 0) return;
    const scroller = scrollerRef.current;
    const pane = scroller?.children[startIndex] as HTMLElement | undefined;
    if (!scroller || !pane) return;

    scroller.scrollTo({ top: pane.offsetTop, behavior: "auto" });
    setCurrent(startIndex);
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

  // The URL follows the reel. Reported from an effect rather than from the
  // observer callback so it fires once per settled item, not once per
  // intersection threshold crossed on the way past it.
  useEffect(() => {
    if (currentItem) onCurrentChange?.(currentItem);
  }, [currentItem, onCurrentChange]);

  useEffect(() => {
    if (!exhausted && current >= items.length - PREFETCH_MARGIN) onLoadMore?.();
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

  const isVideo = currentItem?.kind === "video";

  /**
   * The reel is vertical, so the axes mean different things.
   *
   * Up/Down move between clips, which is the direction the column actually
   * scrolls. Left/Right move through *time* when a video is on screen — the
   * mapping every video player already has — and fall back to moving between
   * items for a still, where there is no time to move through.
   */
  useKeyboardNav({
    onPrev: () => step(-1),
    onNext: () => step(1),
    onSeekBack: isVideo ? () => playback.seekBy(-5) : () => step(-1),
    onSeekForward: isVideo ? () => playback.seekBy(5) : () => step(1),
    onClose,
    onToggleFullscreen: () => void toggle(),
    onTogglePlay: isVideo ? playback.togglePaused : undefined,
    onToggleMuted: isVideo ? playback.toggleMuted : undefined,
  });

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

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
          position={`${current + 1}${exhausted ? ` of ${items.length}${truncated ? "+" : ""}` : ""}`}
          isFullscreen={isFullscreen}
          fullscreenSupported={supported}
          onToggleFullscreen={() => void toggle()}
          onClose={onClose}
          onRename={onRename && ((name) => onRename(currentItem, name))}
          onDelete={onDelete && (() => onDelete(currentItem))}
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
                  active={index === current}
                  muted={playback.muted}
                  onVideoRef={playback.register(item.key)}
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

      {isVideo && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex flex-col items-center
                        gap-2 bg-gradient-to-t from-black/80 to-transparent px-3 pb-4 pt-12">
          {playback.blocked && (
            <Text variant="caption" className="text-white/90">
              Your browser blocked sound. Press play, then unmute.
            </Text>
          )}

          <div className="flex w-full max-w-2xl items-center gap-2">
            <VideoScrubber playback={playback} />

            <button
              type="button"
              onClick={playback.toggleMuted}
              aria-label={playback.muted ? "Unmute (m)" : "Mute (m)"}
              title={playback.muted ? "Unmute (m)" : "Mute (m)"}
              className="pointer-events-auto shrink-0 rounded-full bg-black/55 p-3 text-white/85
                         transition-colors hover:bg-black/75 hover:text-white
                         focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                className="size-5 fill-none stroke-current stroke-[1.5]"
              >
                <path d="M11 5 6 9H3v6h3l5 4Z" />
                {playback.muted ? (
                  <path d="m16 9 5 6m0-6-5 6" />
                ) : (
                  <path d="M15.5 8.5a5 5 0 0 1 0 7M18 6a9 9 0 0 1 0 12" />
                )}
              </svg>
            </button>
          </div>
        </div>
      )}

      {loading && (
        <div className="absolute bottom-24 left-1/2 z-10 -translate-x-1/2">
          <Spinner size="sm" label="Loading more" />
        </div>
      )}
    </div>
  );
}
