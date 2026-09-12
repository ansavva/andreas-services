import { Checkbox } from "@ansavva/design-system";

import type { FileEntry } from "../../types";
import { useFavorites } from "../../hooks/useFavorites";
import { MediaThumb } from "../media/MediaThumb";
import { ActionMenu, type MenuAction } from "../common/ActionMenu";
import { CheckIcon, HeartFilledIcon } from "../common/icons";

interface Props {
  file: FileEntry;
  selected?: boolean;
  /** True once anything in the grid is selected. See the note on `onClick`. */
  selectionActive?: boolean;
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
  /**
   * Where a press on the checkbox goes — **and whether there is a checkbox.**
   *
   * Optional, because a grid with nothing to do to a selection should not offer
   * one: the favorites screen has no move, copy or delete toolbar behind it, so
   * a checkbox there is a control that collects an answer nobody asks for. The
   * browser passes this and gets the full selecting tile.
   */
  onToggleSelect?: (extend: boolean) => void;
  /**
   * Everything that can be done to this picture, as the `⋮` menu's lines.
   *
   * **Composed by the caller, because what is possible depends on the screen
   * and not on the tile.** The browser can rename, move and delete; the
   * favorites grid can do none of those and offers a way off the screen
   * instead. Empty or absent draws no trigger at all.
   */
  actions?: readonly MenuAction[];
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
  selected = false,
  selectionActive = false,
  onOpen,
  to,
  onToggleSelect,
  actions,
}: Props) {
  const favorite = useFavorites().isFavorite(file.id);

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
    if (selectionActive && onToggleSelect) onToggleSelect(event.shiftKey);
    else onOpen();
  };

  const surface = `relative block h-full w-full overflow-hidden border bg-card
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
          // An anchor drags its own href by default, which would drop a URL
          // into the sheet rather than a node. The `MediaThumb` inside is the
          // draggable thing and loads the node itself — see `dragRef` — so
          // the anchor's own drag is switched off rather than overridden.
          draggable={false}
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
      {onToggleSelect && (
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
        className={`absolute left-1.5 top-1.5 shadow-[0_0_0_1px_var(--color-overlay-scrim)] transition-opacity
                    focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100
                    pointer-coarse:opacity-100 ${selectionActive ? "opacity-100" : "opacity-0"}`}
      >
        <Checkbox.Indicator>
          <CheckIcon className="size-3.5 fill-none stroke-current stroke-[3]" />
        </Checkbox.Indicator>
      </Checkbox.Root>
      )}

      {/*
        The menu, opposite the checkbox, and the only control drawn over the
        picture now.

        **A heart and a `Use as reference` glyph used to live here**, revealed on
        hover and permanently drawn on touch, where there is no hover to reveal
        them with. Two 32px targets over a photograph on a phone is the thing
        this replaced: the actions are lines with words in them now — a menu on
        a pointer, a sheet on a phone — and the tile is a picture again. See
        `ActionMenu`.

        Hidden until hovered, always drawn on touch: the same rule the checkbox
        beside it follows, and for the same reason.
      */}
      {actions && actions.length > 0 && (
        <ActionMenu
          label={file.name}
          actions={actions}
          overlay
          vertical
          className="absolute right-1.5 top-1.5 opacity-0 focus-within:opacity-100
                     group-hover:opacity-100 pointer-coarse:opacity-100"
        />
      )}

      {/*
        **A filled heart stays, and it is not a control.**

        It answers "have I already picked this one", which is the one thing on
        this tile that has to be readable without pressing anything — a grid
        that only shows it on hover cannot be read at a glance. Favoriting and
        unfavoriting are lines in the menu; this is the state they leave behind,
        so it is `aria-hidden` and takes no presses. Bottom left, clear of both
        the checkbox and the menu.
      */}
      {favorite && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-1.5 left-1.5 flex size-5 items-center
                     justify-center rounded-pill bg-overlay-scrim/70"
        >
          <HeartFilledIcon className="size-3 fill-current stroke-none text-danger" />
        </span>
      )}

    </div>
  );
}
