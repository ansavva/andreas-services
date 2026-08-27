import { Checkbox } from "@ansavva/design-system";

import type { FileEntry } from "../../types";
import { MediaThumb } from "../media/MediaThumb";

interface Props {
  file: FileEntry;
  selected: boolean;
  /** True once anything in the grid is selected. See the note on `onClick`. */
  selectionActive: boolean;
  onOpen: () => void;
  onToggleSelect: (extend: boolean) => void;
}

/**
 * One image or video in the grid, with the selection behaviour a grid needs.
 *
 * The media itself is `MediaThumb` — the poster frame, the duration chip, the
 * expired-URL re-sign and the lazy loading all live there now, because seven
 * other surfaces wanted the same things and had between none and two of them.
 * What is left here is what makes this a *browser* tile: the checkbox, the
 * selection ring, and the press that means "extend" once a selection exists.
 */
export function MediaTile({
  file,
  selected,
  selectionActive,
  onOpen,
  onToggleSelect,
}: Props) {
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
        <MediaThumb
          nodeId={file.id}
          url={file.url}
          name={file.name}
          isVideo={file.kind === "video"}
          aspect="auto"
          dimmed={selected}
          showName
          // The checkerboard is for the images this library is full of that
          // carry alpha — a pose plate on a dark theme is otherwise a black
          // square. The zoom is this grid's own hover, not every tile's.
          mediaClassName="alpha-checker transition-transform duration-200 group-hover:scale-[1.03]"
        />
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
