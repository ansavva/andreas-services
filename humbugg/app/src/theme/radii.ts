// Humbugg's corners.
//
// `@ansavva/tokens` has made every radius except `pill` 0 since 0.18.0 — the
// package's base is deliberately square — and Humbugg followed it. That left
// one shape out of step: the account menu's trigger, a hard-coded 999px pill
// hanging a hard-cornered rectangle off itself. Rounding is Humbugg's, so it
// is stated here rather than borrowed.
//
// This scale is the ONE place it is stated. The app's own surfaces import it
// directly, and `humbuggTheme` hands the corner steps to `ThemeProvider`, which
// is how the design system's own components take them (0.19.0 added `radii` and
// `fonts` to the provider — before that the native leaves read the tokens at
// module load and no consumer could reach them).
//
// The web half of Humbugg says the same thing in its own idiom: the
// `--radius-*` block in `marketing/src/styles.css`. Keep the two in step by
// hand — same numbers, different units.
export const radii = {
  none: 0,
  xs: 4,
  /** Menu rows, nav links — anything that nests inside a rounded surface. */
  sm: 6,
  /** The working radius: inputs, buttons, panels, popovers, the account menu. */
  md: 10,
  /** Cards and the other page-level surfaces. */
  lg: 14,
  pill: 999,
} as const;
