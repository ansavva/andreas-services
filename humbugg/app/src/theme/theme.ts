// Humbugg's brand, expressed through the design system's native theming seam.
//
// The values themselves live in `brand-colors.json` and `brand-colors.dark.json`,
// and the light thirteen still originate from the `@theme` block in the marketing
// site's `src/styles.css`. Keep those in step by hand; the light JSON and the
// Cognito sign-in pages are kept in step mechanically, by `npm run brand:check` on
// every PR. The DARK thirteen are checked against nothing external on purpose:
// Managed Login renders one scheme, so there is no dark sign-in page to match.
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

import { radii } from './radii';

import humbuggDark from './brand-colors.dark.json';
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


/** The two schemes. The reader picks, or defers to the OS — see `scheme-preference.tsx`. */
export type Scheme = 'light' | 'dark';

/**
 * Every colour the app draws with, resolved per scheme.
 *
 * NO LONGER SAFE TO READ STATICALLY, and that is the whole of this change: a
 * colour baked into a module-scope `StyleSheet.create` cannot follow the scheme,
 * and until dark existed both schemes resolved to the same values so nothing
 * noticed. Reach these through `useTheme()` in `theme/styles.ts`, which selects
 * on `useResolvedScheme()` at render time. The records are still built once, here.
 *
 * The design system's own defaults come from the MATCHING scheme
 * (`colors.dark` under dark), which is what supplies `success` / `warning` /
 * `danger` — status colours Humbugg has never overridden and which need to be
 * legible on a dark ground, not merely inherited from the light record.
 *
 * Below the thirteen roles are Humbugg's own tokens, which have no place in the
 * provider (§0 rule 1):
 *
 * - `frame` / `frameText` — the deep band the marketing hero stacks behind its card.
 * - `scrim` — the dialog backdrop (`bg-ink/60` on the web app).
 * - `shadow` and `depth` — depth is NOT a semantic colour. Every shadow in
 *   `styles.ts` used to be drawn in `ink`, which is cream under dark: each card
 *   grew a pale halo instead of a shadow. A shadow is near-black on a dark page
 *   and carries more of it, because there is less contrast to work with.
 * - `popover` — the fill under a floating surface. `card` barely separates from
 *   `bg` in either scheme (1.04:1 on cream, 1.13:1 here) and light makes up the
 *   difference with the ink shadow, which a dark page cannot show. So a dark
 *   popover lifts by getting lighter instead.
 */
type AppTokens = {
  frame: string;
  frameText: string;
  scrim: string;
  shadow: string;
  depth: { card: number; hero: number; menu: number; mark: number; reveal: number };
  popover: string;
};

const app: Record<Scheme, AppTokens> = {
  light: {
    frame: '#173f35',
    frameText: '#fffdf8',
    scrim: 'rgba(24, 51, 43, 0.6)',
    shadow: '#18332b',
    depth: { card: 0.05, hero: 0.13, menu: 0.15, mark: 0.18, reveal: 0.2 },
    popover: '#fffdf8',
  },
  dark: {
    frame: '#1b3a31',
    frameText: '#f2ece0',
    scrim: 'rgba(4, 12, 10, 0.72)',
    shadow: '#000000',
    depth: { card: 0.4, hero: 0.5, menu: 0.55, mark: 0.45, reveal: 0.5 },
    popover: '#1b352d',
  },
};

/** Every design-system role, plus Humbugg's own tokens. */
export type Palette = Readonly<Record<keyof (typeof colors)['light'], string>> & AppTokens;

export const palettes: Record<Scheme, Palette> = {
  light: { ...colors.light, ...humbugg, ...app.light },
  dark: { ...colors.dark, ...humbuggDark, ...app.dark },
};

/**
 * Registered font-family names.
 *
 * React Native resolves exactly ONE family name — it cannot take a CSS stack —
 * so a font is a real asset that has to be loaded through `expo-font` before it
 * can be named. That is why these are `OpenSans_600SemiBold` rather than
 * `Open Sans, sans-serif`: the weight is part of the family, and asking for
 * `fontWeight: '600'` on top of it would double-apply on some platforms.
 *
 * HEADINGS ARE SANS. Humbugg set them in Spectral until this change; it now
 * runs on one text family, Open Sans, with weight and size doing the work a
 * second family used to. The only face left that is not Open Sans is the
 * wordmark, which is a logo rather than type.
 *
 * `heading` and `body` go to `ThemeProvider` as well as to `theme/styles.ts`,
 * so the design system's own components set in Open Sans too. They did not until
 * design-system 0.21.0: the native leaves set no body family at all and fell
 * through to the platform sans, which put every Button label, Field label and
 * Input value in San Francisco beside Humbugg's own copy. `pill`-shaped
 * glyphs — Select's chevron, Checkbox's tick — deliberately keep the platform
 * face, so a tick never depends on the brand face having that character.
 */
export const fonts = {
  heading: 'OpenSans_600SemiBold',
  headingMedium: 'OpenSans_500Medium',
  body: 'OpenSans_400Regular',
  bodyMedium: 'OpenSans_500Medium',
  bodySemibold: 'OpenSans_600SemiBold',
  bodyBold: 'OpenSans_700Bold',
  wordmark: 'LilyScriptOne_400Regular',
} as const;

/**
 * The provider's theme.
 *
 * Last in the file because it now reads `fonts` below as well as the colours
 * above — a const cannot reference a later one at module scope.
 *
 * `light` is a genuine partial override: only the roles Humbugg changes.
 * `success` / `warning` / `danger` / `dangerHover` are absent because the web
 * app never overrode them either — it reads the package's own values through
 * `var(--color-danger)` and friends.
 *
 * `dark` is Humbugg's own dark thirteen, the same roles inverted: the page
 * becomes the deep green the ink used to be, and `primary` rises to a mint that
 * can carry dark text on top of it. It is a genuine partial override like
 * `light`, so `success` / `warning` / `danger` come from the package's DARK
 * defaults rather than its light ones.
 *
 * The scheme itself is NOT set here. It is `ThemeProvider`'s own `scheme` prop,
 * added in design-system 0.22.0 and driven by `SchemePreferenceProvider` — a
 * theme override says what each scheme looks like, and the provider says which
 * one is painted. Before 0.22.0 the package's native leaves read
 * `useColorScheme()` with no seam to force it, so an in-app switch could move
 * Humbugg's own surfaces and would leave every Button, Input and Select on the
 * system setting; that is why there was no switch until now.
 */
export const humbuggTheme: ThemeOverrides = {
  light: humbugg,
  dark: humbuggDark,
  // Corners and faces, through the same provider as the colours (0.19.0 added
  // `radii` and `fonts`, 0.21.0 made `fonts.body` reach every control). Both
  // are read at render time by the native leaves, so a Button, an Input, a
  // Field label and Humbugg's own text now round and set alike. `pill` is
  // pinned by the package and is not ours to pass — Switch, Avatar and Badge
  // are drawing a shape, not rounding a corner.
  radii: { none: radii.none, xs: radii.xs, sm: radii.sm, md: radii.md, lg: radii.lg },
  fonts: { heading: fonts.heading, body: fonts.body },
};
