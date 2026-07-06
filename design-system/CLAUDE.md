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
│   ├── styles/theme.css                # design tokens (Tailwind v4 @theme) — brand palette
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

## Brand: "Evergreen × Heritage"

`src/styles/theme.css` holds the real Andreas Services brand tokens (not placeholders):

- **Raw palette** (stable across themes): `forest`, `fern`, `ivory`, `linen`, `brass`,
  `clay`.
- **Semantic tokens** (redefined under `[data-theme="dark"]`, so component code never
  branches on theme): `ink`/`muted`/`line` (text/border), `bg`/`card`/`surface-alt`/`frame`
  (surfaces), `accent` (brass — links, focus rings, "look here" detail, active
  tabs/tags), `danger` (clay — destructive actions only, never decorative), `primary`/
  `primary-hover`/`primary-active`/`primary-text` (forest — primary buttons and
  affirmative on/off state: checked checkboxes/radios/switches).
- Dark-mode values are derived with CSS `color-mix()` directly in `theme.css`, matching
  the brand spec's `mix(a, b, x%)` formulas — not hand-picked hex values.
- Fonts (Spectral heading / Archivo body) are loaded via `<link>` tags in the consuming
  app's HTML `<head>` (see README), **not** a CSS `@import` in `theme.css` — a nested
  `@import` gets silently dropped once bundled since it's no longer the first rule in the
  flattened stylesheet.

Component source should never hardcode a raw palette color for something that needs to
adapt between light/dark — always use the semantic token (e.g. `bg-primary`, not
`bg-forest`) unless the surface is deliberately meant to stay stable across both themes
(e.g. `Tooltip` uses `bg-forest`/`text-ivory` directly so it stays legible regardless of
page theme).
