/**
 * Does this prompt cite anything the API has to fill?
 *
 * **The one question `PATCH /api/runs/<id>/plan` is asked.** Sending a prompt as
 * `template` means "expand this"; sending it without means "these are the words".
 * Getting the question wrong in either direction is expensive: a prompt that
 * cites a block and is not sent as a template reaches the model with `{block.…}`
 * in it, and a prompt that cites nothing and IS sent as a template used to be
 * refused for every brace it happened to contain.
 *
 * **That second failure is why this exists.** The test was `prompt.includes("{")`,
 * and `studio prompt` writes a prompt as **serialised JSON** — so
 * `{"subject": …, "camera": {…}}` was sent as a template and came back as
 * "this prompt cites { "subject"}, which nothing provides". A JSON prompt could
 * not be sent from the app at all, and neither could prose with one stray brace
 * in it.
 *
 * So a brace run counts only when it is SHAPED like a citation, which is the
 * rule `services/template.py` now fills by — `CITATION` there is this pattern,
 * written the same way on purpose. The two have to agree: this decides whether
 * the API is asked to expand, and the API decides what expanding does.
 */

/** A member name — also what every block name matches. */
const MEMBER = "[a-z_][a-z0-9_]*";

/**
 * `{block.<name>}`, `{character.<N>.<member>}` with an optional `.face`/`.body`,
 * `{character.<member>}`, or `{slot.<member>}`. Nothing else is a citation.
 *
 * The unnumbered `{character.top}` is deliberately in here. It does not resolve
 * — a character is named by its POSITION — but it is unmistakably an attempt to
 * cite one, so it goes to the API and comes back as the sentence that says how
 * to spell it. Left out, it would reach the model as prose.
 */
export const CITATION = new RegExp(
  "\\{(?:" +
    `block\\.${MEMBER}` +
    `|character\\.(?:[0-9]+\\.${MEMBER}(?:\\.(?:face|body))?|${MEMBER})` +
    `|slot\\.${MEMBER}` +
    ")\\}",
);

/** Whether `text` holds at least one citation the API has to fill. */
export function citesTemplate(text: string): boolean {
  return CITATION.test(text);
}
