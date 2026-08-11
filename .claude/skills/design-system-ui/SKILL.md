---
name: design-system-ui
description: >-
  Repo rule. Build every UI change in andreas-services from @ansavva/design-system —
  check the catalogue before writing a component, import from the package root so the
  bundler picks the platform leaf, and express brand through the theming seams rather
  than hard-coded colours. Use before adding or changing any screen, form, dialog or
  styled component in humbugg/web, humbugg/app or website/.
---

# UI in this repo comes from the design system

`@ansavva/design-system` is published from
[ansavva/design-system](https://github.com/ansavva/design-system) and is the **only** component
library in this monorepo. There is no local one, and there must not become one.

Four consumer skills — `design-system-catalogue`, `design-system-platforms`,
`design-system-setup`, `design-system-theming` — describe how the package itself works. They are
installed by `scripts/dev-setup.sh` and this skill points at them rather than restating them. What
follows is the part that is **ours**: the rules for working in this repo.

## 1. Check the catalogue before you write a component

Hand-rolling something the package already ships is the failure this skill exists to prevent.

- `node_modules/@ansavva/design-system/README.md` — ships in the tarball, so it matches the version
  you actually installed. Read it for "does this exist and what is it called".
- The workbench, <https://ansavva.github.io/design-system/> — every component rendered with its web
  leaf and native leaf **side by side**. Read it for "what does it look like".

→ `design-system-catalogue` for the five shelves, compound components (`Dialog.Trigger`, never a
`DialogTrigger` export), the controlled/uncontrolled pair every input supports, and why `Field`
composes with a control rather than rendering one.

## 2. Import from the package root — never a `.web` or `.native` path

```tsx
import { Button, Field, Input } from '@ansavva/design-system';  // ✅
import { Button } from '@ansavva/design-system/button.web';      // ❌
```

Every component is a `.web.tsx` / `.native.tsx` pair behind one extensionless export, and **your
bundler picks the leaf**. An explicit leaf path hard-codes one platform at the call site — and it
compiles cleanly, so nothing tells you until the other platform renders wrong.

→ `design-system-platforms` for the three-file split and the resolution failure table.

## 3. Know which surface you are in

| Directory | Bundler | Leaf | Styling |
|---|---|---|---|
| `humbugg/web` (marketing, `www.humbugg.com`) | Vite | `.web.tsx` | Tailwind v4 + `theme.css` |
| `website/frontend` (`www.andreas.services`) | Vite | `.web.tsx` | Tailwind v4 + `theme.css` |
| `humbugg/app` (product, `app.humbugg.com`) | Metro | `.native.tsx` | **No Tailwind** — RN `StyleSheet` |

`humbugg/app` is a React Native codebase that also runs in a browser through `react-native-web`. It
keeps its native leaf there — that is deliberate, not a bug, and it is why there is no Tailwind
pipeline on that side. Reaching for a Tailwind class string in `humbugg/app` means you are in the
wrong mental model.

If `react-native-web` turns up in a **web** bundle, something reached a `.native` leaf. Check for an
explicit `.native` import or a resolver whose extension order puts `.native` first.

## 4. Never hard-code a colour, font or radius a semantic role covers

Both sites have an established brand and it is expressed through the design system's theming seams,
not through literals at call sites:

- **Web** — override the CSS custom properties *after* importing `theme.css`. Roles are kebab-case:
  `primaryText` is `--color-primary-text`. Dark mode is the `[data-theme='dark']` selector.
  Typography is `--font-heading` / `--font-body`.
- **Native** — one `ThemeProvider` at the root of `humbugg/app/app/_layout.tsx`.

Raw palette names are exported nowhere, in either direction. That is deliberate: it is what keeps a
re-brand a one-place change. If you want one, the role you need is missing — say so upstream rather
than hard-coding a hex.

**Two traps that bite in this repo specifically:**

- **On native, derived states are pre-computed, not live blends.** Overriding `primary` does *not*
  move `primaryHover` / `primaryActive` — on web they follow via `color-mix()`, on native they do
  not. Humbugg's pressed greens must be set explicitly. The symptom is "the button is our colour
  until you press it".
- **Theme overrides are a loose record, so a misspelled role key is silently ignored** — you get a
  default-coloured component, not an error. Check spelling against the role table.

→ `design-system-theming` for the full role list and both seams.

## 5. When the package is genuinely missing something

Compose from what exists, or raise it upstream in `ansavva/design-system`. Do **not** start a local
component library, and do not vendor a copy.

Some absences are documented and intentional — menubar, navigation menu, number field, scroll area,
context menu, preview card — because each needs a desktop-first interaction model with no touch
counterpart. Those are decisions, not gaps waiting to be filled locally.

Some platform differences are intentional too: native `Popover` and `Dropdown` have no press-outside
dismissal, because React Native has no document to listen to. Give those an explicit close
affordance rather than working around the package.

Before filing a difference as a bug, compare the two leaves in the workbench. If they disagree
*there*, it is the package's problem; if they agree there and not here, it is our resolution or our
theming.

## 6. Installing and staying current

Both packages live on GitHub Packages, which requires a token for **every** read — there is no
anonymous install. The committed `.npmrc` reads `${NODE_AUTH_TOKEN}`; get one with
`eval "$(./scripts/github-packages-auth.sh --export)"`. A `401`/`404` on the `@ansavva` scope almost
always means unauthenticated, not missing.

This is a `0.x` package, and npm's caret rules for `0.x` are narrower than most people expect:
`^0.13.0` means `>=0.13.0 <0.14.0`. **A minor release does not reach you until you widen the range
yourself.** Read `node_modules/@ansavva/design-system/CHANGELOG.md` before widening — it ships in the
tarball, so it needs no network. A struck-through prop in your editor is a deprecation with a
deadline, not a suggestion; fix it before widening again, because under `0.x` caret rules you take
every removal since your last move in one step.

→ `design-system-setup` for the `.npmrc`, the Tailwind `@source` line the package needs, and the
failure table.
