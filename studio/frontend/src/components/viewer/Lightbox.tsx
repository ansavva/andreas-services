import { useCallback, useEffect, useRef, useState } from "react";

import { useFullscreen } from "../../hooks/useFullscreen";
import { useKeyboardNav } from "../../hooks/useKeyboardNav";
import { useSwipe } from "../../hooks/useSwipe";
import type { FileEntry } from "../../types";
import { MediaSurface } from "./MediaSurface";
import { ViewerChrome } from "./ViewerChrome";

interface Props {
  items: FileEntry[];
  startIndex: number;
  onClose: () => void;
}

/** Fullscreen viewer over one folder's media, navigated as a filmstrip. */
export function Lightbox({ items, startIndex, onClose }: Props) {
  const [index, setIndex] = useState(startIndex);
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const { isFullscreen, supported, toggle } = useFullscreen(containerRef);

  const clamp = useCallback(
    (next: number) => Math.min(Math.max(next, 0), items.length - 1),
    [items.length],
  );

  const prev = useCallback(() => setIndex((i) => clamp(i - 1)), [clamp]);
  const next = useCallback(() => setIndex((i) => clamp(i + 1)), [clamp]);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }, []);

  useKeyboardNav({
    onPrev: prev,
    onNext: next,
    onClose,
    onToggleFullscreen: () => void toggle(),
    onTogglePlay: togglePlay,
  });

  const swipe = useSwipe(prev, next);

  // The overlay covers the page, so the page behind it must not scroll — on
  // touch especially, where the rubber-band would drag the whole app.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  const current = items[index];
  if (!current) return null;

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="true"
      aria-label={current.name}
      className="fixed inset-0 z-50 bg-black"
      {...swipe}
    >
      <ViewerChrome
        file={current}
        position={`${index + 1} of ${items.length}`}
        isFullscreen={isFullscreen}
        fullscreenSupported={supported}
        onToggleFullscreen={() => void toggle()}
        onClose={onClose}
      />

      <div className="absolute inset-0 flex items-center justify-center p-2 sm:p-8">
        <MediaSurface
          key={current.key}
          file={current}
          variant="lightbox"
          onVideoRef={(element) => {
            videoRef.current = element;
          }}
        />
      </div>

      {index > 0 && <StepButton side="left" label="Previous" onClick={prev} />}
      {index < items.length - 1 && <StepButton side="right" label="Next" onClick={next} />}

      {/* Neighbours are warmed so a swipe lands on a decoded image rather than a
          blank frame. Presigned URLs are per-object, so this is just a fetch. */}
      <div className="hidden">
        {[items[index - 1], items[index + 1]].map((neighbour) =>
          neighbour && neighbour.kind === "image" ? (
            <img key={neighbour.key} src={neighbour.url} alt="" aria-hidden="true" />
          ) : null,
        )}
      </div>
    </div>
  );
}

function StepButton({
  side,
  label,
  onClick,
}: {
  side: "left" | "right";
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`absolute top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/45 p-3 text-white/85
                  transition-colors hover:bg-black/70 hover:text-white
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                  ${side === "left" ? "left-2 sm:left-4" : "right-2 sm:right-4"}`}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" className="size-6 fill-none stroke-current stroke-[1.5]">
        <path d={side === "left" ? "M15 5 8 12l7 7" : "M9 5l7 7-7 7"} />
      </svg>
    </button>
  );
}
