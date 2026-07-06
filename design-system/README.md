# @ansavva/design-system

Shared React design system for andreas-services (storybook, humbugg, scout), built on
[Base UI](https://base-ui.com/react) and styled with Tailwind CSS v4.

## Install

This package publishes to GitHub Packages, not the public npm registry. Add a `.npmrc` in
your app (or `~/.npmrc`) so npm knows where to resolve the `@ansavva` scope:

```
@ansavva:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

Then:

```bash
npm install @ansavva/design-system
```

## Usage

Import the theme once in your app's Tailwind v4 CSS entrypoint, and point `@source` at
this package's compiled output so Tailwind generates CSS for the utility classes used
inside it:

```css
@import "tailwindcss";
@import "@ansavva/design-system/theme.css";
@source "../node_modules/@ansavva/design-system/dist";
```

Also add the brand fonts (Spectral + Archivo) to your HTML `<head>` — they're not bundled
via CSS `@import` (see `theme.css` for why: a nested `@import` gets silently dropped once
bundled, and Google Fonts recommends `<link>` tags for render performance anyway):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=Spectral:wght@400;500;600;700&display=swap">
```

```tsx
import { Button } from '@ansavva/design-system';

function Example() {
  return <Button intent="primary">Save changes</Button>;
}
```

## Theme

Dark mode toggles by setting `data-theme="dark"` on a root element (e.g. `<html
data-theme="dark">`) — every component reads theme-reactive semantic tokens
(`--color-ink`, `--color-bg`, `--color-primary`, etc.), so nothing in component code
needs to change per theme. See `src/styles/theme.css` for the full token set.

## Local development

```bash
npm install
npm run storybook
```

See `CLAUDE.md` for architecture notes, the component pattern, and publishing.
