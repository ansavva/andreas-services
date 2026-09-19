/**
 * What a citation looks like — the one description of it in the app.
 *
 * A template is prose with mentions in it: `@block.face_only` is shared prose
 * a person wrote, `@character.1.top` is filled from the first character's
 * bible, `@slot.identity` from where the identity images landed. Four places
 * read them — the editor draws them as pills, the preview writes the blocks
 * out, the template page warns about names nothing provides, and the create
 * bar decides whether a prompt has to be sent to the API as a template at all
 * — and they used to hold four regexes that agreed by luck. One shape now, and
 * it is `CITATION` in `services/template.py`, written the same way on purpose:
 * this decides whether the API is asked to fill, and the API decides what
 * filling does, so the two have to say the same thing.
 *
 * **It was `{block.face_only}` until 2026-09-18.** A brace was a code
 * convention shown to people — the menu opened on `{`, which nobody guesses —
 * and an `@` is what every editor a person has used means by "name a thing
 * here". A closing delimiter went with the braces: a mention ends where its
 * name does, which is why the pattern has to say what a name looks like rather
 * than reading up to a `}`. The API rewrites stored rows on the way out, so
 * nothing here ever sees a brace.
 *
 * **An `@` is a citation only when it is SHAPED like one.** A stray `@`,
 * `@ f/2.8`, an e-mail address (the lookbehind: an `@` inside a word is not a
 * mention), a mistyped namespace — all are prose and reach the model as
 * written. The unnumbered `@character.top` is deliberately IN the shape: it
 * does not resolve, but it is unmistakably an attempt to cite one, so it goes
 * to the API and comes back as the sentence that says how to spell it.
 */

/** A member name — also what every block name matches. */
const MEMBER = "[a-z_][a-z0-9_]*";

/** The shapes after the `@`, one alternation, shared by both patterns below. */
const SHAPES =
  `block\\.${MEMBER}` +
  `|character\\.(?:[0-9]+\\.${MEMBER}(?:\\.(?:face|body))?|${MEMBER})` +
  `|slot\\.${MEMBER}`;

const SOURCE = `(?<![A-Za-z0-9_])@(?:${SHAPES})`;

/** One citation, anywhere in a string. */
export const CITATION = new RegExp(SOURCE);

/** Where a citation's value comes from, and what colour it is drawn in. */
export type Namespace = "block" | "character" | "slot";

export interface Citation {
  /** The dotted name after the `@`: `block.face_only`, `character.1.top`. */
  name: string;
  namespace: Namespace;
  /** Offsets into the string, `end` exclusive — `text.slice(start, end)` is `@name`. */
  start: number;
  end: number;
}

/** Every citation in `text`, in order, with where each one sits. */
export function citationsIn(text: string): Citation[] {
  const found: Citation[] = [];
  for (const match of text.matchAll(new RegExp(SOURCE, "g"))) {
    const name = match[0].slice(1);
    found.push({
      name,
      namespace: name.split(".", 1)[0] as Namespace,
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  return found;
}

/** The block a citation names, or null when it names a computed value. */
export function blockNamed(name: string): string | null {
  return name.startsWith("block.") ? name.slice(6) : null;
}

/** Whether `text` holds at least one citation the API has to fill. */
export function citesTemplate(text: string): boolean {
  return CITATION.test(text);
}
