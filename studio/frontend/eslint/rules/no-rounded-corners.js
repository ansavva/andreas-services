import { makeClassTokenRule } from "../utils/makeClassTokenRule.js";

/**
 * `rounded-none` is the corner this app has; `rounded-pill` is a SHAPE (a
 * circle or a stadium), not a corner radius, and stays — see the comment in
 * `styles/app.css` above `--radius-pill`. Everything else in the `rounded`
 * family is the squircle studio spent #589-#596 removing.
 */
const ALLOWED = new Set(["rounded-none", "rounded-pill"]);

function hasBadRounded(text) {
  return text.split(/\s+/).some((token) => {
    if (!token) return false;
    if (token !== "rounded" && !token.startsWith("rounded-")) return false;
    return !ALLOWED.has(token);
  });
}

export default makeClassTokenRule({
  description: "Studio is square: no corner radius but rounded-none (rounded-pill stays a shape).",
  test: hasBadRounded,
  message: "Studio is square: use rounded-none.",
});
