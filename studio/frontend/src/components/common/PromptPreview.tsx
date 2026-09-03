import { useMemo } from "react";
import type { ReactNode } from "react";

import { Field } from "@ansavva/design-system";

/**
 * The prompt with its blocks written out, beside the template being edited.
 *
 * **A template is mostly citations, so the box does not show most of what the
 * prompt says.** `face_front` is four lines of visible text and five block
 * names; the words that actually reach the model are somewhere else on the
 * page, collapsed. Editing one and judging the result meant expanding a block,
 * reading it, collapsing it and reassembling the whole thing in your head.
 *
 * ## What this is NOT
 *
 * It is not the assembled prompt, and it must not claim to be. Assembly turns a
 * character's bible into `{top}`, `{style}`, `{build}` and the rest, and that
 * logic lives in `backend/studio_core/services/reference.py` — one
 * implementation, deliberately, because two opinions about what a run was told
 * to render disagree invisibly after the fact. This substitutes BLOCKS, which is
 * a dictionary lookup and no part of that reasoning, and shows every remaining
 * placeholder as the hole it still is.
 *
 * The fully assembled text, character included, is on the Shoot tab, where a
 * character has been chosen and the answer is a real one.
 *
 * ## One pass, like the backend
 *
 * `assemble` is a single `string.Formatter().vformat`, so a block citing another
 * block is not expanded there either. Expanding it here would show a prompt the
 * pipeline will never produce.
 */
export function PromptPreview({
  prompt,
  blocks,
}: {
  prompt: string;
  blocks: Record<string, string>;
}) {
  const parts = useMemo(() => expand(prompt, blocks), [prompt, blocks]);

  return (
    <PreviewBox
      name="assembled"
      label="Preview"
      description="Blocks written out. Values from the character are filled when you shoot."
      ariaLabel="Assembled preview"
    >
        {parts.map((part, index) => {
          if (part.kind === "text") return <span key={index}>{part.text}</span>;
          if (part.kind === "unfilled") {
            // Not dropped and not left bare. Dropping it would show a sentence
            // the model never sees; leaving it as plain text would read as
            // prose somebody forgot to finish.
            return (
              <span
                key={index}
                className="box-decoration-clone rounded-none border border-dashed border-muted px-1 text-muted"
              >
                {part.text}
              </span>
            );
          }
          // **Expanded prose, still labelled with where it came from.**
          // Unlabelled, the preview is a wall of text and the question it
          // exists to answer — "which of these words can I go and change?" —
          // has no answer in it. The label is the name to look for on the
          // Blocks tab.
          return (
            <Filled key={index} label={`{block.${part.name!}}`} name={part.name!}>
              {part.text}
            </Filled>
          );
      })}
    </PreviewBox>
  );
}

/**
 * A stretch of prose that came from somewhere, labelled with where.
 *
 * **Shared by the two previews, because it answers the same question on both.**
 * A reference angle's preview writes its blocks out; a run plan's writes its
 * cast out. Either way the result is a wall of text in which nothing says which
 * words a reader can go and change, and the label is the name to look for.
 *
 * `box-decoration-clone`: these are paragraphs, so the span wraps over four or
 * five lines and the default paints the background as one ragged shape open at
 * both ends — which reads as a rendering fault rather than as a highlight.
 */
export function Filled({
  label,
  name,
  children,
}: {
  label: string;
  name: string;
  children: ReactNode;
}) {
  return (
    <span
      data-block={name}
      className="box-decoration-clone rounded-none bg-surface-alt px-1 text-ink"
    >
      <span
        data-label=""
        className="mr-1 rounded-none bg-line px-1 text-xs leading-6 text-ink"
      >
        {label}
      </span>
      {children}
    </span>
  );
}

/**
 * A prompt, shown as a prompt.
 *
 * **Shared so the two places that show one cannot drift.** The reference spec's
 * preview and the Shoot tab's assembled prompt are the same object at two
 * stages — one with the character's values still to come — and they were a
 * bordered box beside an editor on one screen and a bare paragraph under a card
 * on the other.
 *
 * `Field.Root` on a box that takes no input, deliberately: it is what makes the
 * label and description exactly as tall as a real field's, so a preview beside
 * an editor starts at the same y and their lines sit on one grid. Eyeballing a
 * caption into place got them a few pixels apart, which on two columns of the
 * same monospace text reads as a rendering fault.
 *
 * `bg-card` is the page's own card colour, so expanded blocks have somewhere
 * darker AND lighter to stand against; `leading-6` and no scroller, because it
 * clipped at 28rem and scrolled on its own, so the first line you saw was
 * whichever one it was resting on rather than the first line of the prompt.
 */
export function PreviewBox({
  name,
  label,
  description,
  ariaLabel,
  children,
}: {
  name: string;
  label: string;
  description: string;
  ariaLabel: string;
  children: ReactNode;
}) {
  return (
    <Field.Root name={name}>
      <Field.Label>{label}</Field.Label>
      <Field.Description>{description}</Field.Description>
      <div
        aria-label={ariaLabel}
        className="rounded-none border border-line bg-card p-2 font-mono text-sm leading-6 whitespace-pre-wrap"
      >
        {children}
      </div>
    </Field.Root>
  );
}

const PLACEHOLDER = /\{[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*\}/g;

type Part =
  | { kind: "text" | "unfilled"; text: string; name?: undefined }
  | { kind: "block"; text: string; name: string };

function expand(prompt: string, blocks: Record<string, string>): Part[] {
  const parts: Part[] = [];
  let at = 0;
  PLACEHOLDER.lastIndex = 0;
  let found = PLACEHOLDER.exec(prompt);
  while (found !== null) {
    const start = found.index;
    const end = start + found[0].length;
    // `{{` and `}}` are a literal brace, which is text rather than a citation.
    if (prompt[start - 1] !== "{" && prompt[end] !== "}") {
      if (start > at) parts.push({ kind: "text", text: prompt.slice(at, start) });
      const cited = found[0].slice(1, -1);
      // `{block.scale_face}` and the legacy `{scale_face}` are the same block.
      // `{character.top}` and `{slot.angle}` are filled at shoot time and stay
      // holes here — this screen has no character.
      const name = cited.startsWith("block.") ? cited.slice(6) : cited;
      const block = cited.includes(".") && !cited.startsWith("block.")
        ? undefined
        : blocks[name];
      parts.push(
        block === undefined
          ? { kind: "unfilled", text: found[0] }
          : { kind: "block", text: block, name },
      );
      at = end;
    }
    found = PLACEHOLDER.exec(prompt);
  }
  if (at < prompt.length) parts.push({ kind: "text", text: prompt.slice(at) });
  return parts;
}
