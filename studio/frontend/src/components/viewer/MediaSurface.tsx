import { forwardRef } from "react";

import { useSignedSrc } from "../../hooks/useSignedSrc";
import type { FileEntry } from "../../types";

interface Props {
  file: FileEntry;
  /** Reel panes autoplay the snapped item; the lightbox gives full controls. */
  variant: "lightbox" | "reel";
  active?: boolean;
  muted?: boolean;
  onVideoRef?: (element: HTMLVideoElement | null) => void;
}

/**
 * One image or video, fitted to whatever box it is given.
 *
 * `object-contain` in both variants: a media reviewer needs to see the whole
 * frame including its aspect ratio, and the bucket mixes 1:1, 9:16 and 16:9
 * output from the same run family. Cropping to fill would hide exactly the
 * thing being judged.
 */
export const MediaSurface = forwardRef<HTMLDivElement, Props>(function MediaSurface(
  { file, variant, active = true, muted = true, onVideoRef },
  ref,
) {
  const { src, failed, onError } = useSignedSrc(file.key, file.url);

  if (failed) {
    return (
      <div ref={ref} className="flex h-full w-full items-center justify-center p-6 text-center">
        <p className="font-body text-sm text-muted">
          This file could not be loaded. It may have been removed from the bucket.
        </p>
      </div>
    );
  }

  if (file.kind === "video") {
    return (
      <div ref={ref} className="flex h-full w-full items-center justify-center">
        <video
          ref={onVideoRef}
          src={src}
          onError={onError}
          // The reel drives play/pause from the intersection observer, so its
          // panes get no controls and no autoplay attribute — an autoplaying
          // offscreen pane is exactly what the observer exists to prevent.
          controls={variant === "lightbox"}
          loop={variant === "reel"}
          muted={muted}
          playsInline
          preload={active ? "auto" : "metadata"}
          className="max-h-full max-w-full object-contain"
        />
      </div>
    );
  }

  return (
    <div ref={ref} className="flex h-full w-full items-center justify-center">
      <img
        src={src}
        alt={file.name}
        onError={onError}
        decoding="async"
        className="max-h-full max-w-full object-contain"
      />
    </div>
  );
});
