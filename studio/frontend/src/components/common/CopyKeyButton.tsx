import { IconButton } from "@ansavva/design-system";

import { copyLabel, useCopyToClipboard, type CopyStatus } from "../../hooks/useCopyToClipboard";
import { CheckIcon, ClipboardIcon, WarningIcon } from "./icons";

type Tone = "row" | "tile" | "chrome";

interface Props {
  /**
   * The slash-joined *name* path — a file's, or a folder's. Copied verbatim.
   *
   * Not the S3 key, which this used to say it was: a blob lives under its
   * owning entity's id, so the two have not matched since the catalog. What
   * lands on the clipboard is what a `studio` command takes, and the CLI
   * resolves it through `GET /api/resolve` — an **address**, not a key and no
   * longer anything a write is aimed at. See `types/index.ts`.
   */
  value: string;
  /**
   * What `value` names — the only thing that differs between the labels.
   *
   * Usually `"path"`, but free text so a bulk copy can say what it is copying
   * ("26 paths"). That is what lets the grid's selection bar use this button
   * rather than growing a second copy control with its own glyph, its own
   * flash timing and its own idea of what "copied" looks like.
   */
  noun?: string;
  /** Which surface this sits on. See `toneStyles`. */
  tone?: Tone;
  className?: string;
}

/**
 * Copies one node's address to the clipboard.
 *
 * It exists once rather than per surface because the address is the thing you
 * reach for from everywhere — a thumbnail, a file row, the open viewer — and a
 * button that looked or behaved differently in each of those places would be
 * three affordances to learn instead of one. Only the paint changes, through
 * `tone`.
 *
 * The name is from when that address was an S3 key. It is a name path now (see
 * `value`), and the label already says so — "Copy path", not "Copy key". The
 * component's own name survives because it is what the surrounding components
 * call this one in their own comments — worth renaming only alongside those.
 *
 * It is always a *sibling* of whatever opens the resource, never a child: every
 * card, row and tile in this app is itself a `<button>`, and a button inside a
 * button is invalid HTML that browsers resolve by dropping one of them.
 *
 * **The box is the design system's `IconButton` now, not a hand-rolled one.**
 * What that buys is the part this file kept getting subtly wrong on its own:
 * the accessible name is a *required prop*, so a nameless copy button is no
 * longer expressible, and the focus ring, the disabled treatment and the hover
 * fill come from the same three rows every other icon control in the monorepo
 * uses. Only `tone` is left here, because only the *surface* is studio's.
 */
export function CopyKeyButton({ value, noun = "path", tone = "row", className = "" }: Props) {
  const { status, copy } = useCopyToClipboard();
  const label = copyLabel(status, `Copy ${noun}`);

  return (
    <IconButton
      label={label}
      // `sm` (32px) rather than `md`: this sits beside `Button size="sm"` in a
      // text page's toolbar and inside a dense file row, and the package
      // documents `sm` as exactly that deliberate opt-in to a smaller target.
      size="sm"
      onClick={() => void copy(value)}
      className={`touch-target shrink-0 ${toneStyles[tone]} ${className}`}
    >
      {/* `aria-live` on the icon's label, so a screen reader hears the outcome
          of a press whose only other feedback is a colour change. */}
      <span className="sr-only" aria-live="polite">
        {status === "idle" ? "" : label}
      </span>
      <StatusIcon
        status={status}
        className={`${tone === "tile" ? "size-4" : "size-5"} fill-none stroke-current stroke-[1.5] ${statusStroke[status]}`}
      />
    </IconButton>
  );
}

/**
 * The three surfaces an address is copied from. `chrome` deliberately matches
 * the object screen's own buttons — it sits in that row and must not read as a
 * different kind of control.
 *
 * **All three used to be written in `white/NN` and `black/NN`**, then in the
 * raw ramp (`neutral-1`, `neutral-a11`, `neutral-a5`) once that existed. Both
 * were the same mistake at different resolutions: a literal nothing could
 * re-brand. `chrome-scrim`/`chrome-muted`/`chrome-ink`/`chrome-hover` are
 * `styles/app.css`'s names for a control floating over media it cannot see
 * the colour of — the same tokens `MediaPlayer`'s own chrome buttons wear.
 */
const toneStyles: Record<Tone, string> = {
  row: "text-muted hover:text-ink",
  tile: "bg-chrome-scrim/80 text-chrome-muted hover:bg-chrome-scrim/95 hover:text-chrome-ink",
  chrome: "text-chrome-muted hover:bg-chrome-hover hover:text-chrome-ink",
};

/** Outcome beats tone: a copied tick is green on a photograph too. */
const statusStroke: Record<string, string> = {
  idle: "",
  copied: "stroke-success",
  failed: "stroke-danger",
};

/** The three states this button reports, as the three glyphs that say them. */
function StatusIcon({ status, className }: { status: CopyStatus; className: string }) {
  if (status === "copied") return <CheckIcon className={className} />;
  if (status === "failed") return <WarningIcon className={className} />;
  return <ClipboardIcon className={className} />;
}
