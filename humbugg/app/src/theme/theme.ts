// Humbugg's brand, expressed through the design system's native theming seam.
//
// The values themselves live in `brand-colors.json`, and they still originate
// from the `@theme` block in the marketing site's `src/styles.css` — this is a
// re-homing of values that already exist, not a colour-picking exercise. Keep
// those two in step by hand; the JSON and the Cognito sign-in pages are kept in
// step mechanically, by `npm run brand:check` on every PR.
//
// THREE THINGS TO KNOW BEFORE EDITING THIS FILE
//
// 1. Speak the SEMANTIC layer only. The package exports no raw palette names,
//    deliberately: overriding roles is what keeps a re-brand a one-place
//    change. Anything with no role is app-level styling and lives in
//    `theme/styles.ts` (see `frame` / `frameText` below).
//
// 2. On native, derived states are PRE-COMPUTED, not live blends. On web
//    `primaryHover` / `primaryActive` follow `primary` through `color-mix()`;
//    on native they are plain token values, so overriding `primary` alone
//    leaves them at the package's navy defaults. The symptom is "the button is
//    our colour until you press it". Humbugg's `#17483a` / `#113b30` are
//    therefore set explicitly, and so is `accentHover`.
//
// 3. `ThemeOverrides` is a loose `Record<string, string>`, so a MISSPELLED role
//    key is silently ignored — you get a default-coloured component, not a type
//    error. Every key below is checked against the role list in
//    `@ansavva/tokens`: bg, card, surfaceAlt, ink, brand, primary, primaryText,
//    accent, muted, line, success, warning, danger, primaryHover,
//    primaryActive, accentHover, dangerHover.
import type { ThemeOverrides } from '@ansavva/design-system';
import { colors } from '@ansavva/tokens';

import humbugg from './brand-colors.json';

/**
 * Humbugg's semantic roles. Partial by design — `success`, `warning`, `danger`
 * and `dangerHover` are deliberately absent because the web app never
 * overrode them either; it reads the package's own values through
 * `var(--color-danger)` and friends.
 *
 * They live in `brand-colors.json` rather than inline because the Cognito
 * Managed Login pages need the same thirteen values, and the tool that writes
 * them (`tool/reconcile-cognito-branding.ts`) cannot import this file: it would
 * pull in `@ansavva/tokens`, whose entry point is TypeScript under
 * `node_modules`, which Node refuses to type-strip. Data both sides can read is
 * the only way to keep the sign-in page and the app one colour.
 */

/**
 * The provider's theme.
 *
 * `light` is a genuine partial override: only the roles Humbugg changes.
 * `success` / `warning` / `danger` / `dangerHover` are absent because the web
 * app never overrode them either — it reads the package's own values through
 * `var(--color-danger)` and friends.
 *
 * `dark` is the light TOKENS with the same Humbugg roles on top, which pins the
 * whole app to one scheme. Humbugg has exactly one visual scheme today: the web
 * app's `styles.css` defines no `[data-theme='dark']` block at all, and the
 * package's dark defaults are a different brand entirely (navy and gold).
 * Leaving `dark` unset would mean an OS-dark user sees a Humbugg that is not
 * Humbugg; inventing a dark palette here would be a redesign, which this port
 * explicitly is not. When Humbugg designs a dark scheme, this is the one line
 * to change.
 */
export const humbuggTheme: ThemeOverrides = {
  light: humbugg,
  dark: { ...colors.light, ...humbugg },
};

/**
 * Every colour the app draws with, resolved once.
 *
 * Safe to read statically — which the design system normally warns against,
 * because a colour baked into `StyleSheet.create` can never follow the OS
 * scheme. It is safe *here* precisely because `humbuggTheme` above resolves both
 * schemes to the same values, so there is nothing for a static read to get
 * wrong. If Humbugg ever gains a real dark scheme, every consumer of this
 * object has to move to `useNativeColors()` at render time.
 *
 * `frame` and `frameText` are Humbugg's own tokens, not design-system roles, so
 * they live here rather than in the provider (§0 rule 4).
 */
export const brand = {
  ...colors.light,
  ...humbugg,
  frame: '#173f35',
  frameText: '#fffdf8',
  /** Semi-transparent ink, for the dialog scrim (`bg-ink/60` on the web app). */
  scrim: 'rgba(24, 51, 43, 0.6)',
} as const;

/**
 * Registered font-family names.
 *
 * React Native resolves exactly ONE family name — it cannot take a CSS stack —
 * so a font is a real asset that has to be loaded through `expo-font` before it
 * can be named. That is why these are `Spectral_600SemiBold` rather than
 * `Spectral, Georgia, serif`: the weight is part of the family, and asking for
 * `fontWeight: '600'` on top of it would double-apply on some platforms.
 *
 * The design system's own native leaves reach for the platform SANS
 * (`lib/native-typography.native.ts` — iOS `System`, Android `sans-serif`) and
 * offer no font seam, so Humbugg's headings are set at our call sites through
 * `theme/styles.ts`. It was the platform serif until design-system 0.18.0,
 * whose base theme dropped the display face entirely: `fonts.heading` and
 * `fonts.body` are now the same stack, because a distinct heading family is a
 * brand decision the base declines to make. Humbugg makes it — Spectral, below
 * — and `ThemeProvider` still cannot carry it: `ThemeOverrides` is `light`/
 * `dark` colour records and nothing else, so fonts AND radii reach the native
 * leaves only through `@ansavva/tokens` itself.
 */
export const fonts = {
  heading: 'Spectral_600SemiBold',
  headingMedium: 'Spectral_500Medium',
  body: 'Archivo_400Regular',
  bodyMedium: 'Archivo_500Medium',
  bodySemibold: 'Archivo_600SemiBold',
  bodyBold: 'Archivo_700Bold',
  wordmark: 'LilyScriptOne_400Regular',
} as const;
