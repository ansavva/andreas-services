import { forwardRef, useMemo, type ReactNode } from "react";

import { TOKEN_CLASS } from "./TokenNode";
import { FAMILY, nextPlaceholder } from "./TokenizedPromptEditor";

/**
 * A prompt read back, drawn the way the create sheet draws it being written.
 *
 * **The same text in the same clothes.** The sheet's editor is body type at
 * `leading-6`, pre-wrapped so a paragraph break is a paragraph break, with
 * every `{placeholder}` as a pill — and the feed row and the opened run's
 * rail drew the same prompt as a plain `Text`: a different face, the line
 * breaks collapsed, and `{character.1.top}` sitting in it as bare braces. A
 * run's prompt is what was in the box when Send was pressed, and it should
 * look like it.
 *
 * **Read-only, and no Lexical.** A feed page holds twenty of these; the
 * editor is an instance each. The pills are the editor's own classes
 * (`TOKEN_CLASS`) over the editor's own scanner (`nextPlaceholder`), so the
 * two cannot drift apart on what a citation looks like or where one starts.
 *
 * **A pill's kind is read off its namespace.** The editor asks the template
 * list which names are blocks; this has no list, and does not need one: a
 * `{block.…}` is a block by construction and every other namespace —
 * `character.N.…`, `slot.…` — is filled from something other than the
 * database. A template lands in the sheet filled, so a stored prompt rarely
 * carries a `{block.…}` at all.
 */
export const PromptText = forwardRef<
  HTMLDivElement,
  {
    text: string;
    className?: string;
    /** `muted` for the negative prompt, which is the prompt's second voice. */
    tone?: "muted";
    /** Set while the feed's clamp is on it — what its measurer reads. */
    "data-clamped"?: string;
  }
>(function PromptText({ text, className = "", tone, ...rest }, ref) {
  const parts = useMemo(() => split(text), [text]);
  return (
    <div
      ref={ref}
      {...rest}
      className={`${FAMILY.body} whitespace-pre-wrap break-words leading-6 ${
        tone === "muted" ? "text-muted" : ""
      } ${className}`}
    >
      {parts}
    </div>
  );
});

/** The text as spans — prose verbatim, each placeholder a pill. */
function split(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let from = 0;
  for (;;) {
    const found = nextPlaceholder(text, from);
    if (found === null) break;
    if (found.start > from) parts.push(text.slice(from, found.start));
    const kind = found.name.startsWith("block.") ? "block" : "computed";
    parts.push(
      <span key={found.start} className={TOKEN_CLASS[kind]} data-token={found.name} data-kind={kind}>
        {found.token}
      </span>,
    );
    from = found.end;
  }
  if (from < text.length) parts.push(text.slice(from));
  return parts;
}
