import { useMemo } from "react";
import type { ReactNode } from "react";

import { Field } from "@ansavva/design-system";

import { blockNamed, citationsIn } from "../../utils/citations";
import type { Namespace } from "../../utils/citations";
import { CITE_FILL, CITE_HOLE, CITE_LABEL } from "./citeStyle";

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
 * character's bible into `@character.1.top`, `.style`, `.build` and the rest,
 * and that logic lives in `backend/studio_core/services/template.py` — one
 * implementation, deliberately, because two opinions about what a run was told
 * to render disagree invisibly after the fact. This substitutes BLOCKS, which is
 * a dictionary lookup and no part of that reasoning, and shows every remaining
 * placeholder as the hole it still is, so a reader can see at a glance how
 * much of the prompt is still to come from the character.
 *
 * The fully assembled text, character included, lands in the create bar when
 * the template is picked there, where a cast exists and the answer is a real one.
 *
 * ## One pass, like the backend
 *
 * The fill scans the template once, so a block citing another block is not
 * expanded there either. Expanding it here would show a prompt the pipeline
 * will never produce.
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
            // prose somebody forgot to finish. Dashed, in the citation tint:
            // a hole, and a hole a character fills.
            return (
              <span
                key={index}
                className={`box-decoration-clone px-1 ${CITE_HOLE[part.namespace]}`}
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
            <Filled key={index} label={`@block.${part.name}`} name={part.name} namespace="block">
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
  namespace,
  children,
}: {
  label: string;
  name: string;
  /** Where these words came from — sets the weight of the tint. */
  namespace: Namespace;
  children: ReactNode;
}) {
  return (
    <span
      data-block={name}
      className={`box-decoration-clone px-1 text-ink ${CITE_FILL[namespace]}`}
    >
      <span
        data-label=""
        className={`mr-1 rounded-pill px-1.5 font-mono text-xs leading-6 ${CITE_LABEL[namespace]}`}
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
        className="rounded-md border border-line bg-card p-2 font-mono text-sm leading-6 whitespace-pre-wrap"
      >
        {children}
      </div>
    </Field.Root>
  );
}

type Part =
  | { kind: "text"; text: string }
  | { kind: "unfilled"; text: string; namespace: Namespace }
  | { kind: "block"; text: string; name: string };

/**
 * The prompt cut into prose, filled blocks and holes.
 *
 * `citationsIn` is the one description of what a citation is, shared with the
 * editor and the API's own pattern — so what this writes out is exactly what
 * the fill will substitute, and a stray `@` is prose here as it is there.
 * `@character.…` and `@slot.…` are filled at shoot time and stay holes: this
 * screen has no character. A `@block.…` naming no block is a hole too, in the
 * same dashed tint, which is the visible half of the warning under the editor.
 */
function expand(prompt: string, blocks: Record<string, string>): Part[] {
  const parts: Part[] = [];
  let at = 0;
  for (const cited of citationsIn(prompt)) {
    if (cited.start > at) parts.push({ kind: "text", text: prompt.slice(at, cited.start) });
    const name = blockNamed(cited.name);
    const block = name === null ? undefined : blocks[name];
    parts.push(
      block === undefined || name === null
        ? { kind: "unfilled", text: prompt.slice(cited.start, cited.end), namespace: cited.namespace }
        : { kind: "block", text: block, name },
    );
    at = cited.end;
  }
  if (at < prompt.length) parts.push({ kind: "text", text: prompt.slice(at) });
  return parts;
}
