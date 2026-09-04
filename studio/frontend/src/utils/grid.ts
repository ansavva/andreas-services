/**
 * The two grids this app draws, as one class string each.
 *
 * **Three media ladders and two entity ladders existed, and none of them was a
 * decision.** Home drew eight tiles across, the folder browser six, the media
 * picker five — the same square tiles at three densities, each chosen when its
 * file was written. A grid is a rhythm the eye learns once per app, so it is
 * set once.
 *
 * Whole literals, not built at the call site: Tailwind finds classes by
 * scanning source text, and a `grid-cols-${n}` is never generated.
 */

/** Characters and projects — a card per cell, one column on a phone. */
export const ENTITY_GRID = "grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3";

/** Images and video — square tiles, three across on a phone. */
export const MEDIA_GRID =
  "grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8";
