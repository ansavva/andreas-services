# Claude Instructions – design-system

## What this is

`@ansavva/design-system` — a shared React component library used across andreas-services
products (storybook, humbugg, scout). It wraps [Base UI](https://base-ui.com/react)
(headless/unstyled primitives from the MUI team) with our brand styling, applied via
Tailwind CSS v4 utility classes and Base UI's `data-*` state attributes.

This is a deliberate exception to the "services share no code" rule elsewhere in this repo —
everything else in andreas-services is fully independent per service.

## Stack

| Layer | Choice |
|---|---|
| Primitives | `@base-ui/react` (headless, unstyled, accessible) |
| Styling | Tailwind CSS v4, tokens defined in `src/styles/theme.css` |
| Class merging | `clsx` + `tailwind-merge` via `cn()` in `src/lib/cn.ts` |
| Build | `tsup` → ESM + CJS + `.d.ts`, `theme.css` copied to `dist/` verbatim |
| Docs/preview | Storybook |
| Tests | Vitest + Testing Library |
| Registry | GitHub Packages (`https://npm.pkg.github.com`), scope `@ansavva` |

## How styling works

Base UI ships **no CSS and no theming system** — only `data-*` attributes reflecting
component state (`[data-checked]`, `[data-open]`, `[data-disabled]`, etc.) and
function-form `className`/`style` props. Every component in this package is a thin
wrapper around a Base UI primitive that:

1. Applies Tailwind utility classes for the base look, using `data-[state=...]:` /
   `data-[checked]:` etc. variants to style state instead of JS conditionals.
2. Accepts a `className` prop merged in last via `cn()` so consumers can override.
3. Reads colors/fonts/radii from the CSS variables defined in `src/styles/theme.css`
   (Tailwind v4 `@theme` block) — never hardcodes a color/font in a component file.

### Consuming apps must

Because Tailwind v4 needs to see the utility classes used inside this package's compiled
output to generate CSS for them, consuming apps must:

```css
/* app's Tailwind entry CSS */
@import "tailwindcss";
@import "@ansavva/design-system/theme.css";
@source "../node_modules/@ansavva/design-system/dist";
```

## Directory structure

```
design-system/
├── src/
│   ├── components/<Name>/<Name>.tsx   # one dir per Base UI primitive
│   ├── lib/cn.ts                       # class-merge helper
│   ├── styles/theme.css                # design tokens (Tailwind v4 @theme) — PLACEHOLDER
│   │                                    # values until the brand style guide is applied
│   └── index.ts                        # barrel export
├── .storybook/                         # docs/preview, imports theme.css + tailwindcss
├── tsup.config.ts                       # build (external: react, react-dom, @base-ui/react)
└── vitest.config.ts
```

## Component pattern

Every component follows the same shape — see any existing component in `src/components/`
for the concrete template. Each Base UI part (e.g. `Dialog.Root`, `Dialog.Trigger`,
`Dialog.Popup`) gets its own styled wrapper, re-exported as a compound component
(`Dialog.Root`, `Dialog.Trigger`, ...).

## Local development

```bash
npm install
npm run storybook   # visual preview at localhost:6006
npm run build        # tsup → dist/
npm run typecheck
npm run lint
npm test
```

## Publishing

Pushing to `main` with changes under `design-system/**` runs
`.github/workflows/design-system-prod.yaml`, which builds and publishes a new version to
GitHub Packages. Bump `version` in `package.json` before merging — the workflow does not
auto-bump.

## Style guide status

`src/styles/theme.css` currently holds **placeholder** token values (generic blue brand
scale, slate neutrals). Replace them with the real andreas-services brand colors/fonts as
soon as they're available — component source shouldn't need to change since everything
reads from these tokens.
