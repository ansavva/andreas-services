import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";

type Tone = "row" | "tile" | "chrome";

interface Props {
  /** The S3 object key, or a folder's prefix. Copied verbatim. */
  value: string;
  /** What `value` names, which is all that differs between the two labels. */
  noun?: "key" | "prefix";
  /** Which surface this sits on. See `toneStyles`. */
  tone?: Tone;
  className?: string;
}

/**
 * Copies one object key to the clipboard.
 *
 * It exists once rather than per surface because the key is the thing you reach
 * for from everywhere — a thumbnail, a file row, the open viewer — and a button
 * that looked or behaved differently in each of those places would be three
 * affordances to learn instead of one. Only the paint changes, through `tone`.
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
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`${tone === "tile" ? "size-4" : "size-5"} fill-none stroke-current stroke-[1.5]
                    ${statusStroke[status]}`}
      >
        {status === "copied" ? (
          <path d="m5 12.5 5 5L19 7" />
        ) : status === "failed" ? (
          <>
            <path d="M12 4 2.5 20.5h19L12 4Z" />
            <path d="M12 10v4.5" />
            <path d="M12 17.5v.01" />
          </>
        ) : (
          <>
            <path d="M9.5 8.5h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1Z" />
            <path d="M15 5.5v-1a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h1" />
          </>
        )}
      </svg>
    </button>
  );
}

/**
 * The three surfaces a key is copied from. `chrome` deliberately matches
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
