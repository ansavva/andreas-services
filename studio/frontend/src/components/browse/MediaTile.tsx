import { Checkbox } from "@ansavva/design-system";

import type { FileEntry } from "../../types";
import { MediaThumb } from "../media/MediaThumb";
import { CheckIcon } from "../common/icons";

interface Props {
  file: FileEntry;
  selected: boolean;
  /** True once anything in the grid is selected. See the note on `onClick`. */
  selectionActive: boolean;
  onOpen: () => void;
  /**
   * Where opening this tile goes, as an address.
   *
   * **Optional, and the reason the tile is an `<a>` at all.** A `<button>` has
   * no new-tab gesture — command-click, middle-click and "open in new window"
   * all do nothing on one — so a grid of media was the one place in the app
   * where the browser's own way of saying "over there, not here" was thrown
   * away. Callers that know the destination pass it; the rest still get a
   * button, which is why this is not required.
   */
  to?: string;
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
  to,
  onToggleSelect,
}: Props) {
  /**
   * Selection mode still wins over the browser, and only for shift.
   *
   * Shift-click is claimed twice — the browser opens a new window with it, the
   * grid extends a selection with it — and inside selection mode the grid's
   * meaning is the one a person means. Command and control are never the
   * grid's, so they always reach the browser.
   */
  const press = (event: React.MouseEvent) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.shiftKey && !selectionActive) return;
    event.preventDefault();
    if (selectionActive) onToggleSelect(event.shiftKey);
    else onOpen();
  };

  const surface = `relative block h-full w-full overflow-hidden rounded-none border bg-card
                    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                    ${selected ? "border-primary ring-2 ring-primary" : "border-line"}`;

  return (
    // The checkbox is a sibling of the tile rather than a child of it: both are
    // <button> elements (the design system's Checkbox.Root is a
    // `role="checkbox"` button) and one cannot contain the other. Clipping
    // stays on the inner button so the focus ring is not cut off.
    <div className="group relative aspect-square">
      {/* Square, not rounded. A grid of media is the one place the corner radius
          is visible against the picture rather than against the page, and a
          rounded frame crops the frame it is meant to present. */}
      {to ? (
        <a
          href={to}
          onClick={press}
          title={file.name}
          aria-current={selectionActive && selected ? "true" : undefined}
          className={surface}
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
            // carry alpha — an angle image on a dark theme is otherwise a black
            // square. The zoom is this grid's own hover, not every tile's.
            mediaClassName="alpha-checker transition-transform duration-200 group-hover:scale-[1.03]"
          />
        </a>
      ) : (
        <button
          type="button"
          // Once anything is selected the grid is in selection mode and a press
          // extends the selection instead of opening — the same bargain every
          // photo library makes, and the only way to pick forty tiles on a
          // touch screen without hunting forty checkboxes.
          onClick={press}
          title={file.name}
          aria-pressed={selectionActive ? selected : undefined}
          className={surface}
        >
          <MediaThumb
            nodeId={file.id}
            url={file.url}
            name={file.name}
            isVideo={file.kind === "video"}
            aspect="auto"
            dimmed={selected}
            showName
            mediaClassName="alpha-checker transition-transform duration-200 group-hover:scale-[1.03]"
          />
        </button>
      )}

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
        // The ring is what keeps a checkbox legible over a pale frame — the
        // media-chrome scrim, since the frame under it is media this app did
        // not choose the colour of.
        className={`absolute left-1.5 top-1.5 shadow-[0_0_0_1px_var(--color-chrome-scrim)] transition-opacity
                    focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100
                    pointer-coarse:opacity-100 ${selectionActive ? "opacity-100" : "opacity-0"}`}
      >
        <Checkbox.Indicator>
          <CheckIcon className="size-3.5 fill-none stroke-current stroke-[3]" />
        </Checkbox.Indicator>
      </Checkbox.Root>
    </div>
  );
}
