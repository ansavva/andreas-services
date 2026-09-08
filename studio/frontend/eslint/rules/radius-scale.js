import { makeClassTokenRule } from "../utils/makeClassTokenRule.js";

/**
 * A corner is one of the design system's six — `none`, `xs`, `sm`, `md`,
 * `lg`, `pill` — on any side. `styles/app.css` sets what `sm`/`md`/`lg`
 * measure (8/12/16px since the ElevenLabs-shaped shell); a call site names
 * the step, never the number. Tailwind's own `xl`/`2xl`/`full` and an
 * arbitrary `rounded-[…]` are the corners that would drift off that scale,
 * and a bare `rounded` is Tailwind's default, which is nothing on this scale.
 *
 * This rule used to be the opposite — "studio is square", `rounded-none` and
 * nothing else — from #589-#596 until the 2026-09 redesign.
 */
const STEP = /^rounded(?:-(?:t|b|l|r|s|e|tl|tr|bl|br|ss|se|es|ee))?-(?:none|xs|sm|md|lg|pill)$/;

function offScale(text) {
  return text.split(/\s+/).some((token) => {
    if (!token) return false;
    // A variant prefix (`md:`, `hover:`) is not the corner.
    const bare = token.slice(token.lastIndexOf(":") + 1);
    if (bare !== "rounded" && !bare.startsWith("rounded-")) return false;
    return !STEP.test(bare);
  });
}

export default makeClassTokenRule({
  description: "A corner radius is a step on the design system's scale: rounded-{none,xs,sm,md,lg,pill}.",
  test: offScale,
  message: "Use a step on the radius scale: rounded-sm, -md, -lg or -pill (rounded-none for a video frame).",
});
