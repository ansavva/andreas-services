import { useState } from "react";

import { Checkbox } from "@ansavva/design-system";

import { useSignedSrc } from "../../hooks/useSignedSrc";
import { formatDuration } from "../../utils/format";
import type { FileEntry } from "../../types";

interface Props {
  file: FileEntry;
  selected: boolean;
  /** True once anything in the grid is selected. See the note on `onClick`. */
  selectionActive: boolean;
  onOpen: () => void;
  onToggleSelect: (extend: boolean) => void;
}

/**
 * One image or video in the grid.
 *
 * Videos get `preload="metadata"` and no poster attribute: the browser paints
 * the first decoded frame, which is a free thumbnail for a bucket that ships no
 * derivatives. Muted + playsInline is what makes that legal on iOS.
 */
export function MediaTile({
  file,
  selected,
  selectionActive,
  onOpen,
  onToggleSelect,
}: Props) {
  const { src, failed, onError } = useSignedSrc(file.id, file.url);
  const [duration, setDuration] = useState<number | null>(null);

  return (
    // The checkbox is a sibling of the tile rather than a child of it: both are
    // <button> elements (the design system's Checkbox.Root is a
    // `role="checkbox"` button) and one cannot contain the other. Clipping
    // stays on the inner button so the focus ring is not cut off.
    <div className="group relative aspect-square">
      <button
        type="button"
        // Once anything is selected the grid is in selection mode and a press
        // extends the selection instead of opening — the same bargain every
        // photo library makes, and the only way to pick forty tiles on a touch
        // screen without hunting forty checkboxes.
        onClick={(event) => (selectionActive ? onToggleSelect(event.shiftKey) : onOpen())}
        title={file.name}
        aria-pressed={selectionActive ? selected : undefined}
        className={`relative block h-full w-full overflow-hidden rounded-md border bg-card
                    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                    ${selected ? "border-primary ring-2 ring-primary" : "border-line"}`}
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
            className={`h-full w-full object-cover transition-transform duration-200
                        group-hover:scale-[1.03] ${selected ? "opacity-75" : ""}`}
          />
        ) : (
          <img
            src={src}
            alt={file.name}
            onError={onError}
            loading="lazy"
            decoding="async"
            className={`alpha-checker h-full w-full object-cover transition-transform duration-200
                        group-hover:scale-[1.03] ${selected ? "opacity-75" : ""}`}
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

      {/* Hidden until it is wanted, so a grid of sixty is not sixty checkboxes
          over the media the app exists to show — but always visible once
          anything is selected (the mode has to be legible) and wherever there
          is no pointer to hover with, because on touch the hidden state is the
          only state. */}
      <Checkbox.Root
        checked={selected}
        onClick={(event) => {
          event.preventDefault();
          onToggleSelect(event.shiftKey);
        }}
        aria-label={`Select ${file.name}`}
        className={`absolute left-1.5 top-1.5 shadow-[0_0_0_1px_rgb(0_0_0/0.6)] transition-opacity
                    focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100
                    pointer-coarse:opacity-100 ${selectionActive ? "opacity-100" : "opacity-0"}`}
      >
        <Checkbox.Indicator>
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="size-3.5 fill-none stroke-current stroke-[3]"
          >
            <path d="m5 12.5 5 5L19 7" />
          </svg>
        </Checkbox.Indicator>
      </Checkbox.Root>
    </div>
  );
}
