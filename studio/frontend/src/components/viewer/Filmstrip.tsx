import { useEffect, useRef } from "react";

import { IconButton, Spinner } from "@ansavva/design-system";

import { MediaThumb } from "../media/MediaThumb";
import { ChevronDownIcon } from "../common/icons";
import type { FileEntry } from "../../types";

/** The chevron is drawn pointing down; these turn it. */
const CHEVRON = "size-5 fill-none stroke-current stroke-[1.5]";

interface Props {
  items: FileEntry[];
  /** The file the page is open on. Scrolled into view as it changes. */
  currentId: string;
  /** A page of the feed is in flight. */
  loading?: boolean;
  onSelect: (file: FileEntry) => void;
  onPrev?: () => void;
  onNext?: () => void;
}

/**
 * The feed's neighbours, running across under the player.
 *
 * **This is what the scroll-snap column became, and the trade was taken with
 * eyes open.** A vertical reel let a thumb flick from one clip to the next and
 * felt native doing it; a strip plus two buttons does not. What it buys is a
 * *page* — the clip stays where it belongs, the neighbours are visible rather
 * than one flick away in the dark, and the stage mounts exactly one `<video>`
 * instead of a five-pane window sized to a decoder budget.
 *
 * The tiles are `MediaThumb`, which withholds its `src` until the box is near
 * the viewport — sixty neighbours off the right-hand edge of the strip cost no
 * requests until they are scrolled to.
 *
 * The arrows are the same step Left/Right take, which is deliberate: a keyboard
 * shortcut nothing on screen mirrors is a shortcut nobody finds.
 */
export function Filmstrip({ items, currentId, loading = false, onSelect, onPrev, onNext }: Props) {
  const strip = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = strip.current;
    const tile = el?.querySelector<HTMLElement>(`[data-node="${currentId}"]`);
    if (!el || !tile) return;

    // **Scroll the strip, never the page.** This was `tile.scrollIntoView({
    // block: "nearest", inline: "center" })`, and `block: "nearest"` is not the
    // no-op it reads as: when the strip is below the fold — which it is at
    // 390px — the browser scrolls every scrollable ANCESTOR to reveal it,
    // including the document. Measured on load at 390px: `window.scrollY` came
    // to rest at 85, which slid the file's own name under the sticky header.
    // Desktop never showed it because the strip is already in view there.
    //
    // Centring by hand touches one scroller and cannot move the page. Computed
    // from rects rather than `offsetLeft`, which is measured from whichever
    // ancestor happens to be positioned.
    const tileBox = tile.getBoundingClientRect();
    const stripBox = el.getBoundingClientRect();
    const left = el.scrollLeft + (tileBox.left - stripBox.left) - (el.clientWidth - tileBox.width) / 2;

    // jsdom implements neither, and this is decoration — the strip is correct
    // whether or not it scrolls itself.
    if (typeof el.scrollTo === "function") el.scrollTo({ left, behavior: "smooth" });
    else el.scrollLeft = left;
  }, [currentId]);

  // One neighbour is no neighbours. A cold `/o/<id>` link resolves to a feed of
  // exactly the file it names, and a strip holding one copy of what is already
  // on the stage says nothing.
  if (items.length < 2) return null;

  return (
    <div className="flex items-center gap-1">
      <IconButton label="Previous (←)" size="sm" disabled={!onPrev} onClick={() => onPrev?.()}>
        <ChevronDownIcon className={`${CHEVRON} rotate-90`} />
      </IconButton>

      <div
        ref={strip}
        aria-label="Neighbours"
        className="no-scrollbar flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto py-1"
      >
        {items.map((item) => {
          const current = item.id === currentId;
          return (
            <button
              key={item.id}
              type="button"
              data-node={item.id}
              aria-current={current ? "true" : undefined}
              onClick={() => onSelect(item)}
              title={item.name}
              /* `relative` is load-bearing, not cosmetic: the `sr-only` span
                 below is `position: absolute`, so without a positioned ancestor
                 here its containing block resolves ABOVE the strip's
                 `overflow-x-auto` — which means the strip does not clip it, and
                 all 71 of them contribute their static position to the ROOT
                 scroller. Measured: `document.documentElement.scrollWidth` was
                 4984 against a 390 viewport (`body` stayed 390), and the page
                 scrolled 4.6k px into empty space at every width. */
              className={`relative w-16 shrink-0 cursor-pointer rounded-xs outline-offset-2
                          focus-visible:outline-2 focus-visible:outline-primary
                          ${current ? "outline outline-2 outline-primary" : "opacity-70 hover:opacity-100"}`}
            >
              {/* The name is on the button's `title` and in this label, so the
                  picture inside it is decorative — see `MediaThumb`. */}
              <span className="sr-only">{item.name}</span>
              <MediaThumb
                nodeId={item.id}
                url={item.url}
                name={item.name}
                isVideo={item.kind === "video"}
                aspect="square"
                className="rounded-xs"
              />
            </button>
          );
        })}

        {loading && (
          <span className="flex shrink-0 items-center px-2">
            <Spinner size="sm" label="Loading more" />
          </span>
        )}
      </div>

      <IconButton label="Next (→)" size="sm" disabled={!onNext} onClick={() => onNext?.()}>
        <ChevronDownIcon className={`${CHEVRON} -rotate-90`} />
      </IconButton>
    </div>
  );
}
