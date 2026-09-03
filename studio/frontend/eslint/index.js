/**
 * Studio's own lint rules, for the patterns a plain `no-restricted-syntax`
 * selector cannot express cleanly — a class string spread across a template
 * literal, a ternary and a hoisted constant; a JSX element's single
 * meaningful child. See `docs/WEB_APP.md`'s "UI vocabulary" section for what
 * each one enforces and the PR that added it. No dependency added: this is
 * plain ESLint rule objects, wired in as a local plugin.
 */
import noRoundedCorners from "./rules/no-rounded-corners.js";
import noNeutralRamp from "./rules/no-neutral-ramp.js";
import noHandRolledButton from "./rules/no-hand-rolled-button.js";
import noGlyphOnlyChild from "./rules/no-glyph-only-child.js";
import noEmptyStateProse from "./rules/no-empty-state-prose.js";

export default {
  rules: {
    "no-rounded-corners": noRoundedCorners,
    "no-neutral-ramp": noNeutralRamp,
    "no-hand-rolled-button": noHandRolledButton,
    "no-glyph-only-child": noGlyphOnlyChild,
    "no-empty-state-prose": noEmptyStateProse,
  },
};
