import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

import studio from "./eslint/index.js";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { "react-hooks": reactHooks, studio },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // ─────────────────────── one visual vocabulary, enforced ───────────────────────
      // Each rule below is a pattern #589-#596 removed by hand; see
      // docs/WEB_APP.md's "UI vocabulary" section for the one-line summary of
      // all nine and the PRs that established them.

      // R1 corner radius — studio is square.
      "studio/no-rounded-corners": "error",
      // R3 raw ramp tokens — colour goes through a semantic role.
      "studio/no-neutral-ramp": "error",
      // R5 literal glyphs — an icon is an SVG, not a character.
      "studio/no-glyph-only-child": "error",

      "no-restricted-syntax": [
        "error",
        {
          // R2 ghost intent — never used here.
          selector: "JSXAttribute[name.name='intent'][value.value='ghost']",
          message: "ghost is not used here; secondary is the quiet intent.",
        },
        {
          selector:
            ":matches(Property[key.name='intent'], Property[key.value='intent'])[value.type='Literal'][value.value='ghost']",
          message: "ghost is not used here; secondary is the quiet intent.",
        },
        {
          // `label` is already a required prop in the type — this is the
          // same rule stated where a reviewer reading a diff sees it, and it
          // still catches a `// @ts-expect-error` or a `.js` call site.
          selector:
            "JSXOpeningElement[name.name='IconButton']:not(:has(JSXAttribute[name.name='label'])):not(:has(JSXSpreadAttribute))",
          message: "Use Button, IconButton or buttonClass from the design system.",
        },
        {
          // R8 the old failure-title forms.
          selector:
            "JSXElement[openingElement.name.object.name='Alert'][openingElement.name.property.name='Title'] > JSXText[value=/^\\s*(That did not|Nothing was)/]",
          message: "Failure titles read 'Could not ‹verb› ‹noun›'.",
        },
        {
          selector:
            "JSXElement[openingElement.name.object.name='Alert'][openingElement.name.property.name='Title'] JSXExpressionContainer > Literal[value=/^(That did not|Nothing was)/]",
          message: "Failure titles read 'Could not ‹verb› ‹noun›'.",
        },
      ],
    },
  },
  {
    // R4 hand-rolled controls — off inside components/common/, where the
    // design-system-wrapping helpers (Chip, TagSelect, Backlinks, …) are
    // exactly the place a raw element is allowed to carry its own classes.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/components/common/**"],
    plugins: { studio },
    rules: { "studio/no-hand-rolled-button": "error" },
  },
  {
    // R7 empty-state prose — off inside EmptyState.tsx itself.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/components/common/EmptyState.tsx"],
    plugins: { studio },
    rules: { "studio/no-empty-state-prose": "error" },
  },
  {
    // R6 spinner label — off in *.test.tsx, where a test of the fallback
    // itself has to render `<ApertureSpinner />` with nothing passed.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          // Every spinner says what it is loading — a missing `label` falls
          // back to the component's own generic default, which is exactly
          // the sentence this rule exists to rule out.
          selector:
            "JSXOpeningElement[name.name='ApertureSpinner']:not(:has(JSXAttribute[name.name='label'])):not(:has(JSXSpreadAttribute))",
          message: "Every spinner says what it is loading.",
        },
      ],
    },
  },
);
