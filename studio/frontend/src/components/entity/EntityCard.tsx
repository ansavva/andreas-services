import { useNavigate } from "react-router-dom";

import { Text } from "@ansavva/design-system";

import type { HeroImage } from "../../types";
import { MediaThumb } from "../media/MediaThumb";
import { isModifiedPress } from "./EntityRow";

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
  /** Where the card goes. An `<a>`, for the same reason `EntityRow` is one. */
  to: string;
}

/**
 * A character or a project, as a card — the one card, beside the one row.
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
 * The whole card is one `<a>`, which is why nothing inside it may be a control.
 */
export function EntityCard({ name, hero, counts, to }: Props) {
  const navigate = useNavigate();

  return (
    <a
      href={to}
      onClick={(event) => {
        if (isModifiedPress(event) || event.shiftKey) return;
        event.preventDefault();
        navigate(to);
      }}
      title={name}
      // Square, and a hairline rather than a filled card. These sit in a grid
      // where a rule alone would not close the shape, so the border stays —
      // what goes is the rounding and the fill that made each one an object
      // floating on the page instead of a cell in a grid. Hover and focus are
      // the row's, so the two shapes answer a pointer the same way.
      className="flex w-full items-center gap-3 rounded-none border border-line p-2 text-left
                 transition-colors hover:bg-surface-alt
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

      {/* The counts get a line of their own because `caption` is a block as of
          design-system 0.17.0. This card is the reason that default changed:
          it read `Name0 references · 54 files` when caption was inline, and
          carried a `className="block"` to fix it — one every caller had to
          remember. `truncate` needs the block box too; an inline box has no
          width to elide against. */}
      <span className="min-w-0 flex-1">
        <Text variant="body" weight="medium" className="truncate">
          {name}
        </Text>
        <Text variant="caption" tone="muted" className="truncate font-mono tabular-nums">
          {counts}
        </Text>
      </span>
    </a>
  );
}
