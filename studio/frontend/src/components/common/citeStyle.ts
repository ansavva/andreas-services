import type { Namespace } from "../../utils/citations";

/**
 * How a citation is coloured, wherever one is drawn.
 *
 * **Three hues, one per namespace, and this is the only file that names
 * them.** `styles/app.css` says why the chrome has a hue here and nowhere
 * else; this says which class carries it, so the pill in the editor, the
 * filled prose in the preview, the row in the `@` menu and the name on the
 * Blocks tab cannot drift apart — a block is violet in all four or the colour
 * stops meaning "a block".
 *
 * Whole literals, because Tailwind finds classes by scanning source text and
 * a `text-cite-${ns}` is never generated.
 *
 * The glow is a `box-shadow` with no offset: a blur of the pill's own hue,
 * which is what makes a pill read as lit from within rather than painted on.
 * `shadow-[0_0_12px]` leaves the colour to `--tw-shadow-color`, which the
 * per-namespace `shadow-cite-*` sets.
 */
export const CITE_TEXT: Record<Namespace, string> = {
  block: "text-cite-block",
  character: "text-cite-character",
  slot: "text-cite-slot",
};

/** A pill: the citation as one atomic thing in a line of prose. */
export const CITE_PILL: Record<Namespace, string> = {
  block:
    "rounded-pill px-1.5 font-mono ring-1 shadow-[0_0_12px] " +
    "bg-cite-block/15 text-cite-block ring-cite-block/40 shadow-cite-block/40",
  character:
    "rounded-pill px-1.5 font-mono ring-1 shadow-[0_0_12px] " +
    "bg-cite-character/15 text-cite-character ring-cite-character/40 shadow-cite-character/40",
  slot:
    "rounded-pill px-1.5 font-mono ring-1 shadow-[0_0_12px] " +
    "bg-cite-slot/15 text-cite-slot ring-cite-slot/40 shadow-cite-slot/40",
};

/**
 * Prose a citation was filled with, in the preview: a tint of the same hue
 * over the paragraph, so a reader can see which words came from where.
 */
export const CITE_FILL: Record<Namespace, string> = {
  block: "bg-cite-block/10",
  character: "bg-cite-character/10",
  slot: "bg-cite-slot/10",
};

/** The label at the front of a filled span: the name, on a stronger tint. */
export const CITE_LABEL: Record<Namespace, string> = {
  block: "bg-cite-block/20 text-cite-block",
  character: "bg-cite-character/20 text-cite-character",
  slot: "bg-cite-slot/20 text-cite-slot",
};

/** A hole the preview cannot fill — a value the character supplies at shoot time. */
export const CITE_HOLE: Record<Namespace, string> = {
  block: "border border-dashed border-cite-block/50 text-cite-block",
  character: "border border-dashed border-cite-character/50 text-cite-character",
  slot: "border border-dashed border-cite-slot/50 text-cite-slot",
};
