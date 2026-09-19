import type { Namespace } from "../../utils/citations";

/**
 * How a citation is coloured, wherever one is drawn.
 *
 * **One hue, and this is the only file that names it.** `styles/app.css` says
 * why the chrome has a hue here and nowhere else; this says which class
 * carries it, so the pill in the editor, the filled prose in the preview, the
 * row in the `@` menu and the name on the Blocks tab cannot drift apart.
 *
 * **The namespace is weight, not hue.** A block is prose somebody wrote and
 * can open; a character or slot value is computed at shoot time and has
 * nothing behind it. The first is the full tint at medium weight, the second
 * the same tint stepped back — and the text says which it is regardless.
 * Three hues were tried, one per namespace, each with a ring and a glow; on a
 * near-monochrome app they read as stickers.
 *
 * Whole literals, because Tailwind finds classes by scanning source text and
 * a `text-cite/${n}` is never generated.
 */
const FULL = "text-cite";
const STEPPED = "text-cite/75";

export const CITE_TEXT: Record<Namespace, string> = {
  block: FULL,
  character: STEPPED,
  slot: STEPPED,
};

/** A pill: the citation as one atomic thing in a line of prose. */
export const CITE_PILL: Record<Namespace, string> = {
  block: `rounded-pill bg-cite/12 px-1.5 font-mono font-medium ${FULL}`,
  character: `rounded-pill bg-cite/8 px-1.5 font-mono ${STEPPED}`,
  slot: `rounded-pill bg-cite/8 px-1.5 font-mono ${STEPPED}`,
};

/**
 * Prose a citation was filled with, in the preview: a faint tint over the
 * paragraph, so a reader can see which words came from where.
 */
export const CITE_FILL: Record<Namespace, string> = {
  block: "bg-cite/8",
  character: "bg-cite/8",
  slot: "bg-cite/8",
};

/** The label at the front of a filled span: the name, on a stronger tint. */
export const CITE_LABEL: Record<Namespace, string> = {
  block: `bg-cite/15 ${FULL}`,
  character: `bg-cite/15 ${STEPPED}`,
  slot: `bg-cite/15 ${STEPPED}`,
};

/** A hole the preview cannot fill — a value the character supplies at shoot time. */
export const CITE_HOLE: Record<Namespace, string> = {
  block: `border border-dashed border-cite/40 ${FULL}`,
  character: `border border-dashed border-cite/40 ${STEPPED}`,
  slot: `border border-dashed border-cite/40 ${STEPPED}`,
};
