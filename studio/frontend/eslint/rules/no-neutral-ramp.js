import { makeClassTokenRule } from "../utils/makeClassTokenRule.js";

function hasNeutralRamp(text) {
  return text.split(/\s+/).some((token) => token.includes("neutral-"));
}

export default makeClassTokenRule({
  description: "No raw neutral-ramp Tailwind classes outside the chrome tokens; use a semantic token.",
  test: hasNeutralRamp,
  message: "Use a semantic token (text-ink, bg-surface-alt…), not the neutral ramp.",
});
