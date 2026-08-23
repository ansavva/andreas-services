import { Text } from "@ansavva/design-system";

import type { HeroImage } from "../../types";

interface Props {
  title: string;
  /** The slug — the address a person types, shown because it is not the title. */
  slug: string;
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
export function EntityCard({ title, slug, hero, counts, onOpen }: Props) {
  return (
    <button
      type="button"
      onClick={onOpen}
      title={slug}
      className="flex w-full items-center gap-3 rounded-md border border-line bg-card p-2 text-left
                 transition-colors hover:bg-surface-alt
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <span className="size-16 shrink-0 overflow-hidden rounded-md border border-line bg-surface-alt">
        {hero ? (
          <img src={hero.url} alt="" className="h-full w-full object-cover" />
        ) : (
          <span className="flex h-full w-full items-center justify-center font-heading text-xl text-muted">
            {title.slice(0, 1).toUpperCase()}
          </span>
        )}
      </span>

      <span className="min-w-0 flex-1">
        <Text variant="body" weight="medium" className="truncate">
          {title}
        </Text>
        <Text variant="caption" tone="muted" className="truncate">
          {slug}
        </Text>
        <Text variant="caption" tone="muted" className="truncate tabular-nums">
          {counts}
        </Text>
      </span>
    </button>
  );
}
