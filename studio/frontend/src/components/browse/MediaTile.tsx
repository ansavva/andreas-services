import { useState } from "react";

import { useSignedSrc } from "../../hooks/useSignedSrc";
import { formatDuration } from "../../utils/format";
import type { FileEntry } from "../../types";
import { CopyKeyButton } from "../common/CopyKeyButton";

interface Props {
  file: FileEntry;
  onOpen: () => void;
}

/**
 * One image or video in the grid.
 *
 * Videos get `preload="metadata"` and no poster attribute: the browser paints
 * the first decoded frame, which is a free thumbnail for a bucket that ships no
 * derivatives. Muted + playsInline is what makes that legal on iOS.
 */
export function MediaTile({ file, onOpen }: Props) {
  const { src, failed, onError } = useSignedSrc(file.key, file.url);
  const [duration, setDuration] = useState<number | null>(null);

  return (
    // The copy button is a sibling of the tile rather than a child of it,
    // because the tile is a <button> and nesting one inside another is invalid.
    // Clipping stays on the inner button so the focus ring is not cut off.
    <div className="group relative aspect-square">
      <button
        type="button"
        onClick={onOpen}
        title={file.name}
        className="relative block h-full w-full overflow-hidden rounded-md border border-line bg-card
                   focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        {failed ? (
          <span className="flex h-full w-full items-center justify-center px-2 text-center text-xs text-muted">
            Unavailable
          </span>
        ) : file.kind === "video" ? (
          <video
            src={src}
            onError={onError}
            onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
            preload="metadata"
            muted
            playsInline
            className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
          />
        ) : (
          <img
            src={src}
            alt={file.name}
            onError={onError}
            loading="lazy"
            decoding="async"
            className="alpha-checker h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
          />
        )}

        {file.kind === "video" && (
          <span
            className="pointer-events-none absolute bottom-1.5 right-1.5 rounded-sm bg-black/70 px-1.5
                       py-0.5 font-body text-[11px] tabular-nums text-white"
          >
            {duration ? formatDuration(duration) : "video"}
          </span>
        )}

        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80
                     to-transparent px-2 pb-1.5 pt-6 text-left font-body text-[11px] text-white/90
                     opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
        >
          {file.name}
        </span>
      </button>

      {/* Revealed on hover or focus so a grid of sixty tiles is not a grid of
          sixty buttons — but unconditionally visible where there is no pointer
          to hover with, because on touch the hidden state is the only state. */}
      <CopyKeyButton
        value={file.key}
        tone="tile"
        className="absolute right-1.5 top-1.5 opacity-0 transition-opacity
                   focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100
                   pointer-coarse:opacity-100"
      />
    </div>
  );
}
