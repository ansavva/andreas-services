/**
 * The blank bible template's own placeholder marker, and how to show one.
 *
 * **These reach a model verbatim.** The template writes `<garment>` and
 * `<one plain colour, optional>` into the fields a person is meant to replace,
 * and `top_text` reads whatever is there — so an unfilled field arrives in the
 * prompt as literal angle brackets and the model is asked to render a
 * `<garment>`. Nothing said so: the assembled prompt showed them in the middle
 * of real prose, in the same weight as the prose, and left it to be noticed.
 *
 * Drawn the same way `PromptPreview` draws a placeholder no block provides,
 * because it is the same fact — a hole that is still a hole. The words inside
 * the marker say what it is, so the styling is a second carrier rather than the
 * only one.
 *
 * Matched on the marker's SHAPE rather than a list of known field names, so a
 * field nobody has thought of is caught too.
 *
 * **It used to require a lowercase letter and three characters**, which missed
 * the two markers most in need of catching: `<Name>`, and the ten fields whose
 * hint was the empty `<>`. Those are the ones a person is likeliest to leave —
 * an empty marker does not say what belongs in it — and they were the ones
 * nothing flagged. The content may now be empty, and anything but a leading
 * space, which is what keeps a stray `a < b … >` in prose from matching.
 */
const UNFILLED = /<(?:[^<>\s][^<>]{0,59})?>/g;

/** Every unfilled marker in `text`, or an empty array. */
export function unfilledIn(text: string): string[] {
  return text.match(UNFILLED) ?? [];
}

/** `text`, with each unfilled marker drawn as the hole it is. */
export function Marked({ text }: { text: string }) {
  const parts: Array<{ mark: boolean; text: string }> = [];
  let at = 0;
  UNFILLED.lastIndex = 0;
  let found = UNFILLED.exec(text);
  while (found !== null) {
    if (found.index > at) parts.push({ mark: false, text: text.slice(at, found.index) });
    parts.push({ mark: true, text: found[0] });
    at = found.index + found[0].length;
    found = UNFILLED.exec(text);
  }
  if (at < text.length) parts.push({ mark: false, text: text.slice(at) });

  return (
    <>
      {parts.map((part, index) =>
        part.mark ? (
          <span
            key={index}
            data-unfilled={part.text}
            className="box-decoration-clone rounded border border-dashed border-neutral-8 px-1 py-0.5 text-muted"
          >
            {part.text}
          </span>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </>
  );
}
