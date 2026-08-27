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
   * Usually `"key"` or `"prefix"`, but free text so a bulk copy can say what it
   * is copying ("26 keys"). That is what lets the grid's selection bar use this
   * button rather than growing a second copy control with its own glyph, its own
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
 * `value`), and the name survives because it is what the surrounding components
 * call this one in their own comments — worth renaming only alongside those.
 *
 * It is always a *sibling* of whatever opens the resource, never a child: every
 * card, row and tile in this app is itself a `<button>`, and a button inside a
 * button is invalid HTML that browsers resolve by dropping one of them.
 */
export function CopyKeyButton({ value, noun = "key", tone = "row", className = "" }: Props) {
  const { status, copy } = useCopyToClipboard();
  const label = copyLabel(status, `Copy ${noun}`);

  return (
    <button
      type="button"
      onClick={() => void copy(value)}
      aria-label={label}
      title={label}
      className={`shrink-0 rounded-md transition-colors
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary
                  ${toneStyles[tone]} ${className}`}
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
    </button>
  );
}

/**
 * The three surfaces an address is copied from. `chrome` deliberately matches
 * `ViewerChrome`'s own buttons — it sits in that row and must not read as a
 * different kind of control.
 */
const toneStyles: Record<Tone, string> = {
  row: "p-2 text-muted hover:bg-surface-alt hover:text-ink",
  tile: "bg-black/55 p-1.5 text-white/85 hover:bg-black/80 hover:text-white",
  chrome: "p-2 text-white/80 hover:bg-white/15 hover:text-white",
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
