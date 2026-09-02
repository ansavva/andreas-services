import { Text } from "@ansavva/design-system";

import type { HeroImage } from "../../types";
import { MediaThumb } from "../media/MediaThumb";

interface Props {
  /**
   * What the entity is called. **The one label there is.**
   *
   * The card used to draw two — a `title` in body text and a `slug` in mono
   * underneath, because a slug was the address a person typed and a title was
   * prose. There is no address to show any more: identity is a UUID, which is
   * not something to put on a card.
   */
  name: string;
  hero: HeroImage | null;
  /** "41 references · 62 files", "12 runs · 2 scenes" — whatever this entity counts. */
  counts: string;
  onOpen: () => void;
}

/**
 * A character or a project, as a card.
 *
 * One component for both because the difference between them is what they count,
 * and that arrives as a formatted string — a second card that differed only in
 * which two numbers it read would be two grids to keep looking alike.
 *
 * **The hero is optional and its absence is ordinary**, not an error state: a
 * character created five minutes ago has no reference images yet, and a project
 * has no hero until a run in it succeeds. So the fallback is the initial rather
 * than a broken-image glyph or a "no image" apology.
 *
 * The whole card is one `<button>`, which is why nothing inside it may be one —
 * the same constraint every row and tile in this app is under.
 */
export function EntityCard({ name, hero, counts, onOpen }: Props) {
  return (
    <button
      type="button"
      onClick={onOpen}
      title={name}
      // Square, and a hairline rather than a filled card. These sit in a grid
      // where a rule alone would not close the shape, so the border stays —
      // what goes is the rounding and the fill that made each one an object
      // floating on the page instead of a cell in a grid.
      className="flex w-full items-center gap-3 rounded-none border border-line p-2 text-left
                 transition-colors hover:bg-card
                 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
    >
      <span className="size-16 shrink-0 overflow-hidden rounded-none border border-line bg-surface-alt">
        {hero ? (
          <MediaThumb nodeId={hero.node} url={hero.url} name="" aspect="auto" />
        ) : (
          <span className="flex h-full w-full items-center justify-center font-heading text-xl text-muted">
            {name.slice(0, 1).toUpperCase()}
          </span>
        )}
      </span>

      {/*
        `block` on both captions, and it is a bug fix rather than tidying.

        `Text variant="body"` renders a `<p>`; `variant="caption"` renders a
        `<span>`, which is **inline**. So these two sat on one line with nothing
        between them and the card read `<label><counts>` run together — literally
        "jason0 references · 54 files" — while `truncate` did nothing at all,
        needing a block box to have a width to truncate against.

        The e2e suite asserts the counts with a regex that still matched as a
        substring, which is why it went unnoticed: nothing was missing from the
        DOM, it was only unreadable.
      */}
      <span className="min-w-0 flex-1">
        <Text variant="body" weight="medium" className="truncate">
          {name}
        </Text>
        {/* The counts are numbers, so mono with `tabular-nums`: it is what
            lines them up between one card and the next. */}
        <Text variant="caption" tone="muted" className="block truncate font-mono tabular-nums">
          {counts}
        </Text>
      </span>
    </button>
  );
}
