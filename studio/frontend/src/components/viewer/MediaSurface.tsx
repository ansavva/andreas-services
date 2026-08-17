import { useSignedSrc } from "../../hooks/useSignedSrc";
import type { FileEntry } from "../../types";

interface Props {
  file: FileEntry;
  /** True for the snapped pane. Drives how eagerly the media is fetched. */
  active?: boolean;
  muted?: boolean;
  onVideoRef?: (element: HTMLVideoElement | null) => void;
}

/**
 * One image or video, fitted to whatever box it is given.
 *
 * `object-contain`: a media reviewer needs to see the whole frame including its
 * aspect ratio, and the bucket mixes 1:1, 9:16 and 16:9 output from the same run
 * family. Cropping to fill would hide exactly the thing being judged.
 *
 * There is no `variant` any more. It existed to tell the reel's panes apart from
 * the lightbox's single frame — chiefly so the lightbox could have native
 * `controls` and the reel could not — and the lightbox is gone. The reel keeps
 * its panes control-less on purpose: the pane is a scroll-snap target, and the
 * browser's control bar sits exactly where the scroll gesture starts. The
 * transport lives in `VideoScrubber` instead, above the frame.
 */
export function MediaSurface({ file, active = true, muted = true, onVideoRef }: Props) {
  const { src, failed, onError } = useSignedSrc(file.key, file.url);

  if (failed) {
    return (
      <div className="flex h-full w-full items-center justify-center p-6 text-center">
        <p className="font-body text-sm text-muted">
          This file could not be loaded. It may have been removed from the bucket.
        </p>
      </div>
    );
  }

  if (file.kind === "video") {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <video
          ref={onVideoRef}
          src={src}
          onError={onError}
          // Play/pause is driven from the snapped index, so there is no
          // `autoplay` attribute either — an autoplaying offscreen pane is
          // exactly what the intersection observer exists to prevent.
          loop
          muted={muted}
          playsInline
          preload={active ? "auto" : "metadata"}
          className="max-h-full max-w-full object-contain"
        />
      </div>
    );
  }

  return (
    <div className="flex h-full w-full items-center justify-center">
      <img
        src={src}
        alt={file.name}
        onError={onError}
        decoding="async"
        className="max-h-full max-w-full object-contain"
      />
    </div>
  );
}
