import { forwardRef, useMemo, type ReactNode } from "react";

import { citationsIn } from "../../utils/citations";
import { CITE_PILL } from "./citeStyle";
import { FAMILY } from "./TokenizedPromptEditor";

/**
 * A prompt read back, drawn the way the create sheet draws it being written.
 *
 * **The same text in the same clothes.** The sheet's editor is body type at
 * `leading-6`, pre-wrapped so a paragraph break is a paragraph break, with
 * every `@citation` as a pill — and the feed row and the opened run's rail
 * drew the same prompt as a plain `Text`: a different face, the line breaks
 * collapsed, and `@character.1.top` sitting in it as bare text. A run's
 * prompt is what was in the box when Send was pressed, and it should look
 * like it.
 *
 * **Read-only, and no Lexical.** A feed page holds twenty of these; the
 * editor is an instance each. The pills are the editor's own classes
 * (`CITE_PILL`) over the one citation scanner (`citationsIn`), so the two
 * cannot drift apart on what a citation looks like or where one starts.
 *
 * **Every citation is a pill here, known or not.** The editor pills only the
 * names its menu offers, because there a half-typed name must stay text;
 * this has no list and no caret, and a stored prompt's citations were all
 * real when it was sent. A template lands in the sheet filled, so a stored
 * prompt rarely carries a `@block.…` at all.
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

/** The text as spans — prose verbatim, each citation a pill. */
function split(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let from = 0;
  for (const found of citationsIn(text)) {
    if (found.start > from) parts.push(text.slice(from, found.start));
    parts.push(
      <span
        key={found.start}
        className={CITE_PILL[found.namespace]}
        data-token={found.name}
        data-namespace={found.namespace}
      >
        {text.slice(found.start, found.end)}
      </span>,
    );
    from = found.end;
  }
  if (from < text.length) parts.push(text.slice(from));
  return parts;
}
