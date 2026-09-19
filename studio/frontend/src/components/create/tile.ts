/**
 * The create sheet's picture tile, as classes — the box, the face, the
 * picture and the caption strip.
 *
 * **One tile, drawn in three places.** The sheet draws it for what a run WILL
 * be handed (`AttachTiles`); the feed row and the opened run's rail draw it
 * for what a run WAS handed (`SendThumbs`). They are the same fact read at
 * two times, and they were drawn as two things: 112px tiles with the word on
 * a scrim there, 80px squares with the word underneath here. Named once so
 * the answer to "what did this run get" looks like the question it answers.
 *
 * Whole strings, because Tailwind finds classes by scanning source text.
 */

/**
 * The box: a fixed height, a floor on the width, and never squeezed by its
 * row. 144px under a coarse pointer, 112px under a mouse — see `Thumb` in
 * `AttachTiles` for why not 72px squares.
 */
export const TILE_BOX = "relative h-28 min-w-20 shrink-0 pointer-coarse:h-36 pointer-coarse:min-w-24";

/** The face the picture sits on: the box's height, the picture's width, rounded, clipped. */
export const TILE_FACE = "relative block h-full w-auto min-w-full overflow-hidden rounded-md bg-fill";

/** The picture in a tile: the tile's full height, its own width, whole. */
export const TILE_MEDIA = "h-full w-auto max-w-[16rem] object-contain";

/**
 * The word over the picture's foot, on a scrim, the way ElevenLabs labels
 * `@Image 1`. Taller under a thumb.
 */
export const TILE_CAPTION =
  "absolute inset-x-0 bottom-0 flex items-center justify-center gap-0.5 truncate rounded-b-md " +
  "bg-overlay-scrim/60 px-1 py-0.5 text-xs font-medium text-overlay-ink pointer-coarse:gap-1.5 pointer-coarse:text-sm";

/** The row the tiles sit in: one line, scrolling sideways rather than wrapping. */
export const TILE_ROW = "flex min-w-0 items-center gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]";
