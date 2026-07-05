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

```tsx
import { Button } from '@ansavva/design-system';

function Example() {
  return <Button intent="primary">Save changes</Button>;
}
```

## Local development

```bash
npm install
npm run storybook
```

See `CLAUDE.md` for architecture notes, the component pattern, and publishing.
