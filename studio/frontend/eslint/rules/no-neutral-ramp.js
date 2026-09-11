import { makeClassTokenRule } from "../utils/makeClassTokenRule.js";

function hasNeutralRamp(text) {
  return text.split(/\s+/).some((token) => token.includes("neutral-"));
}

export default makeClassTokenRule({
  description: "No raw neutral-ramp Tailwind classes; use a semantic role — including `overlay-*` for a control drawn over media.",
  test: hasNeutralRamp,
  message: "Use a semantic role (text-ink, bg-surface-alt, or overlay-* over media), not the neutral ramp.",
});
