/**
 * The one recipe for a button that reads as an inline text link.
 *
 * **The package has no `Link`**, because a link is a `Button` styled with
 * `buttonClass` per its own doc comment — but `buttonClass`'s three weights
 * all carry a fixed height and padding, which is right for a control and
 * wrong for a word sitting mid-sentence. This is that missing weight, typed
 * once instead of three times: `Backlinks`, `OwnerLink` and `RunPage`'s
 * duplicate-run notice each grew their own copy of the same underline, and
 * the corner-radius sweep (#589-#596) found `rounded` on one of the three and
 * not the other two.
 *
 * Two tones, because the callers are two different facts: `accent` is "here
 * is the other thing", `muted` is "here is where this lives" — text you would
 * read past until you needed it.
 */
export function linkButtonClass(tone: "accent" | "muted" = "accent", className = ""): string {
  const base =
    tone === "accent"
      ? "text-sm text-accent underline underline-offset-2 hover:opacity-80"
      : "text-left text-muted underline-offset-2 hover:text-ink hover:underline";
  return `rounded-none ${base} ${className}`.trim();
}
