// Humbugg's bespoke CSS, ported to React Native.
//
// The web app expresses half its appearance through hand-written classes in
// `src/styles.css` (`.hero-card`, `.eyebrow`, `.avatar-chip`, `.status-pill`, …)
// and Tailwind utilities in the page components. None of that carries itself
// over: there is no CSS on this side, so every radius, gap, weight and shadow
// is re-stated here once rather than scattered as literals through screens.
//
// Values are converted straight from the source: `rem` × 16 = px, and each
// `color-mix(in srgb, X n%, Y)` is resolved to its flat result (comments show
// the original).
//
// THE SHEET IS BUILT ONCE PER SCHEME, not once. A colour baked into a
// module-scope `StyleSheet.create` can never follow the scheme, so this file
// exports `useTheme()` rather than a `styles` object: both sheets are created
// eagerly below and the hook picks one on `useResolvedScheme()`. Nothing
// allocates per render. A component with its own local sheet wraps it in
// `scopedStyles`, which does the same two-sheet trick for it.
//
// RADII ARE THE ONE EXCEPTION, and deliberately so. They come from a scale
// rather than from converted literals, because a corner is the one thing here
// the design system's own components also draw — a hard 16 in this file next
// to a `radii.lg` inside `Button` is how the two halves of a screen come to
// disagree. The scale is Humbugg's own (`./radii`): `@ansavva/tokens` has been
// square since 0.6.0, and `humbuggTheme` hands the same scale to the design
// system through `ThemeProvider`, so both halves still move together.
// `marketing/src/styles.css` states the same numbers as `--radius-*` for the
// web half. A pill stays a pill on both — it is a shape, not a corner.
import { StyleSheet } from 'react-native';

import { radii } from './radii';

import { useResolvedScheme } from './scheme-preference';
import { fonts, palettes, type Palette, type Scheme } from './theme';

/** `color-mix(in srgb, <hex> <pct>%, transparent)` as an rgba string. */
function alpha(hex: string, pct: number): string {
  const value = hex.replace('#', '');
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${pct / 100})`;
}

/** `color-mix(in srgb, <top> <pct>%, <bottom>)` flattened to one opaque hex. */
function mix(top: string, pct: number, bottom: string): string {
  const parse = (hex: string) => {
    const value = hex.replace('#', '');
    return [0, 2, 4].map((index) => parseInt(value.slice(index, index + 2), 16));
  };
  const [tr, tg, tb] = parse(top);
  const [br, bg, bb] = parse(bottom);
  const ratio = pct / 100;
  const channel = (t: number, b: number) => Math.round(t * ratio + b * (1 - ratio));
  return `#${[channel(tr!, br!), channel(tg!, bg!), channel(tb!, bb!)]
    .map((n) => n.toString(16).padStart(2, '0'))
    .join('')}`;
}

/** Blends that the CSS computes at paint time and RN cannot. */
function buildBlends(brand: Palette) {
  return {
    /** `.status-error` background — `--color-danger` at 12%. */
    dangerWash: alpha(brand.danger, 12),
    /** `.status-success` background — `--color-primary` at 10%. */
    primaryWash: alpha(brand.primary, 10),
    /** `.avatar-chip` background — primary 12% over card. */
    avatarChip: mix(brand.primary, 12, brand.card),
    /** `.status-drawn` background — accent 18% over card. */
    drawnPill: mix(brand.accent, 18, brand.card),
    /** `border-danger/30` on the danger-zone cards. */
    dangerBorder: alpha(brand.danger, 30),
    /** `border-primary/20` on the organizer panel. */
    primaryBorder: alpha(brand.primary, 20),
    /**
     * `.assignment-label` — primaryText at 65%.
     *
     * Only the light reveal uses it: dark fills the card with `surfaceAlt`
     * rather than `primary`, so its labels are `muted` on that panel instead.
     */
    assignmentLabel: alpha(brand.primaryText, 65),
  } as const;
}

export type Blends = ReturnType<typeof buildBlends>;

function buildStyles(scheme: Scheme, brand: Palette, blends: Blends) {
  const dark = scheme === 'dark';
  return StyleSheet.create({
    // ── Page furniture ────────────────────────────────────────────────────────
    /** `min-h-screen bg-bg text-ink` */
    screen: { flex: 1, backgroundColor: brand.bg },
    /** `mx-auto max-w-7xl px-5 py-10 lg:px-8` */
    main: { width: '100%', maxWidth: 1280, alignSelf: 'center', paddingHorizontal: 20, paddingVertical: 40 },
    /** The rail beside the page — see `Shell`'s `aside`. The card colour, ruled off from the page. */
    aside: {
      width: 420,
      minHeight: 0,
      borderLeftWidth: StyleSheet.hairlineWidth,
      borderLeftColor: alpha(brand.line, 80),
      backgroundColor: brand.card,
    },
    /** The rail folded away: a launcher in the page's corner with the unread count on it. */
    asideLauncher: { position: 'absolute', right: 24, bottom: 24 },
    /** `border-b border-line/80 bg-bg/95` — the sticky header band. */
    header: {
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: alpha(brand.line, 80),
      backgroundColor: brand.bg,
      // The account menu hangs out of this band, and react-native-web gives every
      // View `z-index: 0` — a stacking context each, so the menu's own z-index is
      // sealed inside the header and the scrolling body, a later sibling, painted
      // over it. Raising the band itself is what puts the menu above the page.
      zIndex: 1,
      elevation: 1,
    },
    headerInner: {
      width: '100%',
      maxWidth: 1280,
      alignSelf: 'center',
      height: 80,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 20,
    },
    /** `border-t border-line/80 bg-bg` */
    footer: {
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: alpha(brand.line, 80),
      backgroundColor: brand.bg,
    },
    footerInner: {
      width: '100%',
      maxWidth: 1280,
      alignSelf: 'center',
      gap: 24,
      paddingHorizontal: 20,
      paddingVertical: 40,
    },

    // ── Typography ────────────────────────────────────────────────────────────
    /** `.eyebrow` */
    eyebrow: {
      color: brand.muted,
      fontFamily: fonts.bodyBold,
      fontSize: 12,
      letterSpacing: 2.16, // .18em at 12px
      textTransform: 'uppercase',
    },
    // Headings are Open Sans SemiBold — the same weight the marketing site's
    // `font-semibold` heading classes carry, so the two surfaces match. The
    // negative tracking is the sans tax: Spectral
    // carried these sizes on its own proportions, and a bold grotesque set at 48
    // without it reads wide and loose. It scales with the size and stops at the
    // ones that are display type — 20px and below are set normally.
    /** `font-heading text-5xl font-semibold leading-tight tracking-tight` */
    displayXl: {
      color: brand.ink,
      fontFamily: fonts.heading,
      fontSize: 48,
      lineHeight: 53,
      letterSpacing: -1.2, // -.025em
    },
    /** `font-heading text-4xl font-semibold tracking-tight` */
    displayLg: {
      color: brand.ink,
      fontFamily: fonts.heading,
      fontSize: 36,
      lineHeight: 42,
      letterSpacing: -0.9,
    },
    /** `font-heading text-3xl font-semibold tracking-tight` */
    displayMd: {
      color: brand.ink,
      fontFamily: fonts.heading,
      fontSize: 30,
      lineHeight: 36,
      letterSpacing: -0.6,
    },
    /** `font-heading text-2xl font-semibold` */
    heading: {
      color: brand.ink,
      fontFamily: fonts.heading,
      fontSize: 24,
      lineHeight: 30,
      letterSpacing: -0.36,
    },
    /** `font-heading text-xl font-semibold` */
    headingSm: { color: brand.ink, fontFamily: fonts.heading, fontSize: 20, lineHeight: 26 },
    /** Body copy — Open Sans at the browser default 16px. */
    body: { color: brand.ink, fontFamily: fonts.body, fontSize: 16, lineHeight: 24 },
    /** `text-muted` body copy — `leading-7` where the source used it. */
    bodyMuted: { color: brand.muted, fontFamily: fonts.body, fontSize: 16, lineHeight: 28 },
    /** `text-sm` */
    small: { color: brand.ink, fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
    smallMuted: { color: brand.muted, fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
    /** `text-xs text-muted` */
    tiny: { color: brand.muted, fontFamily: fonts.body, fontSize: 12, lineHeight: 16 },
    /** `font-semibold` inline emphasis. */
    semibold: { fontFamily: fonts.bodySemibold },
    /** `text-accent hover:underline` — every in-app link. */
    link: { color: brand.accent, fontFamily: fonts.bodySemibold, fontSize: 14, lineHeight: 20 },

    // ── Brand marks ───────────────────────────────────────────────────────────
    /** `.brand-mark` — the rotated square lockup. */
    brandMark: {
      width: 40,
      height: 40,
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden',
      borderRadius: radii.md,
      borderWidth: 1,
      borderColor: alpha(brand.primaryText, 16), // the CSS inset ring
      backgroundColor: brand.primary,
      transform: [{ rotate: '-1deg' }],
      shadowColor: dark ? brand.shadow : brand.primary,
      shadowOpacity: brand.depth.mark,
      shadowRadius: 14,
      shadowOffset: { width: 0, height: 5 },
      elevation: 3,
    },
    brandMarkText: { color: brand.primaryText, fontFamily: fonts.wordmark, fontSize: 32 },
    /** `.brand-mark-large` */
    brandMarkLarge: { width: 64, height: 64, borderRadius: radii.lg },
    brandMarkLargeText: { fontSize: 52 },
    /** `.brand-wordmark` */
    wordmark: {
      color: brand.primary,
      fontFamily: fonts.wordmark,
      fontSize: 37.6, // 2.35rem
      letterSpacing: -0.94, // -.025em
    },

    // ── Surfaces ──────────────────────────────────────────────────────────────
    /** `Card` from the web app's Layout: `rounded-lg border border-line bg-card p-6 shadow-sm`. */
    card: {
      borderWidth: 1,
      borderColor: brand.line,
      borderRadius: radii.lg,
      padding: 24,
      backgroundColor: brand.card,
      shadowColor: brand.shadow,
      shadowOpacity: brand.depth.card,
      shadowRadius: 3,
      shadowOffset: { width: 0, height: 1 },
      elevation: 1,
    },
    /** The taller card variant the auth and onboarding screens use (`p-8`). */
    cardRoomy: { padding: 32 },
    /** `.hero-card` */
    heroCard: {
      borderWidth: 1,
      borderColor: brand.line,
      borderRadius: radii.lg,
      padding: 28,
      backgroundColor: brand.card,
      shadowColor: brand.shadow,
      shadowOpacity: brand.depth.hero,
      shadowRadius: 70,
      shadowOffset: { width: 0, height: 24 },
      elevation: 8,
    },
    /** `rounded-xl bg-surface-alt p-5` — the inset panels in the organizer tools. */
    panel: { borderRadius: radii.md, backgroundColor: brand.surfaceAlt, padding: 20 },
    /** `.empty-panel` */
    emptyPanel: {
      borderWidth: 1,
      borderStyle: 'dashed',
      borderColor: brand.line,
      borderRadius: radii.lg,
      paddingVertical: 40,
      paddingHorizontal: 16,
      alignItems: 'center',
    },
    /** `.loading-panel` */
    loadingPanel: { flex: 1, minHeight: 320, alignItems: 'center', justifyContent: 'center', gap: 12 },
    loadingSpinner: { alignSelf: 'center' },

    // ── Status ────────────────────────────────────────────────────────────────
    /** `.status-message` */
    statusMessage: { marginTop: 16, borderRadius: radii.md, paddingVertical: 13, paddingHorizontal: 16 },
    statusMessageText: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
    /** `.status-error` */
    statusError: { backgroundColor: blends.dangerWash },
    statusErrorText: { color: brand.danger },
    /** `.status-success` */
    statusSuccess: { backgroundColor: blends.primaryWash },
    statusSuccessText: { color: brand.primary },
    /** `.status-pill` */
    statusPill: {
      alignSelf: 'flex-start',
      borderRadius: radii.pill,
      paddingVertical: 5,
      paddingHorizontal: 11,
      backgroundColor: brand.surfaceAlt,
    },
    statusPillText: {
      color: brand.primary,
      fontFamily: fonts.bodyBold,
      fontSize: 11.5,
      letterSpacing: 0.92, // .08em
      textTransform: 'uppercase',
    },
    /** `.status-drawn` */
    statusDrawn: { backgroundColor: blends.drawnPill },
    statusDrawnText: { color: brand.ink },
    /** `.count-badge` */
    countBadge: {
      minWidth: 36,
      height: 36,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: radii.pill,
      backgroundColor: brand.surfaceAlt,
      paddingHorizontal: 8,
    },
    countBadgeText: { color: brand.ink, fontFamily: fonts.bodyBold, fontSize: 14 },

    // ── Lists and rows ────────────────────────────────────────────────────────
    /** `.group-row` */
    groupRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16,
      borderWidth: 1,
      borderColor: brand.line,
      borderRadius: radii.md,
      padding: 16,
    },
    groupRowActive: { borderColor: brand.primary },
    /** `.member-row` */
    memberRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 13,
      borderRadius: radii.md,
      padding: 12,
      backgroundColor: brand.surfaceAlt,
    },
    /** `.avatar-chip` */
    avatarChip: {
      width: 36,
      height: 36,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: radii.pill,
      backgroundColor: blends.avatarChip,
    },
    avatarChipText: { color: brand.primary, fontFamily: fonts.heading, fontSize: 15 },
    /** `.pair-chip` */
    pairChip: {
      borderRadius: radii.pill,
      paddingVertical: 6,
      paddingHorizontal: 11,
      backgroundColor: brand.surfaceAlt,
    },
    pairChipText: { color: brand.ink, fontFamily: fonts.body, fontSize: 12 },
    /** `.group-meta span` */
    metaChip: {
      borderWidth: 1,
      borderColor: brand.line,
      borderRadius: radii.pill,
      paddingVertical: 7,
      paddingHorizontal: 12,
      backgroundColor: brand.card,
    },
    /** `.group-heading` */
    groupHeading: { gap: 32, borderBottomWidth: 1, borderBottomColor: brand.line, paddingBottom: 32 },

    // ── The assignment reveal ─────────────────────────────────────────────────
    /**
     * `.assignment-card` — the reveal, and the one surface the two schemes do
     * not share a rule for.
     *
     * On cream it is the single dark block on the page: filled `primary`, cream
     * type. Inverting that under dark would make the brightest thing on screen
     * out of the one card a reader opens at night, so dark raises a panel
     * instead — `surfaceAlt` behind a `primary` border, with the recipient's
     * name and the claim button carrying the mint.
     */
    assignmentCard: {
      borderRadius: radii.lg,
      padding: 32,
      backgroundColor: dark ? brand.surfaceAlt : brand.primary,
      borderWidth: dark ? 1 : 0,
      borderColor: brand.primary,
      shadowColor: dark ? brand.shadow : brand.primary,
      shadowOpacity: brand.depth.reveal,
      shadowRadius: 50,
      shadowOffset: { width: 0, height: 18 },
      elevation: 6,
    },
    /** `.assignment-label` */
    assignmentLabel: {
      marginBottom: 6,
      color: dark ? brand.muted : blends.assignmentLabel,
      fontFamily: fonts.bodyBold,
      fontSize: 11.5,
      letterSpacing: 1.38, // .12em
      textTransform: 'uppercase',
    },
    assignmentText: {
      color: dark ? brand.ink : brand.primaryText,
      fontFamily: fonts.body,
      fontSize: 14,
      lineHeight: 20,
    },
    /** The recipient's name, and anything else the reveal sets in its accent. */
    assignmentHeading: { color: dark ? brand.primary : brand.primaryText },
    /**
     * Colour only, for text on the reveal that already has a size of its own.
     * `assignmentText` and `assignmentLabel` carry a size and would silently
     * resize whatever they were merged onto.
     */
    assignmentInk: { color: dark ? brand.ink : brand.primaryText },
    assignmentSubtle: { color: dark ? brand.muted : blends.assignmentLabel },

    // ── Forms ─────────────────────────────────────────────────────────────────
    /**
     * A `Button` that spans its container — the primary action at the foot of a
     * form or card.
     *
     * Needed explicitly since design-system 0.18.0, which stopped five native
     * leaves stretching to their parent's width: a React Native parent defaults
     * to `alignItems: 'stretch'`, `Button` declared no cross-axis size, and so a
     * button that hugs its label on web ran the full width of the screen on a
     * device. Hugging is the default on both platforms now, which is right for
     * the toolbar and row buttons this app is mostly made of — the handful that
     * really are full-bleed say so here, once, the same way `w-full` says it on
     * the web side.
     */
    buttonBlock: { alignSelf: 'stretch' },
    /** `.field-label` */
    fieldLabel: { gap: 7 },
    fieldLabelText: { color: brand.ink, fontFamily: fonts.bodySemibold, fontSize: 14 },
    /** `.nav-link` */
    navLink: {
      minHeight: 40,
      justifyContent: 'center',
      borderRadius: radii.sm,
      paddingHorizontal: 12,
    },
    navLinkText: { color: brand.muted, fontFamily: fonts.bodySemibold, fontSize: 14 },

    // ── Overlays ──────────────────────────────────────────────────────────────
    /** `fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4` */
    scrim: {
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 16,
      backgroundColor: brand.scrim,
    },
    /** The account menu popover — `rounded-xl border border-line bg-card p-1 shadow-lg`. */
    menu: {
      width: 208,
      overflow: 'hidden',
      borderWidth: 1,
      borderColor: brand.line,
      borderRadius: radii.md,
      padding: 4,
      backgroundColor: brand.popover,
      shadowColor: brand.shadow,
      shadowOpacity: brand.depth.menu,
      shadowRadius: 15,
      shadowOffset: { width: 0, height: 10 },
      elevation: 8,
    },
    menuItem: { borderRadius: radii.sm, paddingVertical: 8, paddingHorizontal: 12 },
    menuItemText: { color: brand.ink, fontFamily: fonts.bodyMedium, fontSize: 14 },
    menuItemDangerText: { color: brand.danger },
  });
}

/** Gaps the source expressed as `space-y-*` / `gap-*`, in one place. */
export const gap = { xs: 8, sm: 12, md: 16, lg: 20, xl: 28, xxl: 32 } as const;

export type Theme = {
  scheme: Scheme;
  brand: Palette;
  blends: Blends;
  styles: ReturnType<typeof buildStyles>;
};

function build(scheme: Scheme): Theme {
  const brand = palettes[scheme];
  const blends = buildBlends(brand);
  return { scheme, brand, blends, styles: buildStyles(scheme, brand, blends) };
}

/** Both sheets, created once at module load. Selecting one is free. */
const themes: Record<Scheme, Theme> = { light: build('light'), dark: build('dark') };

/**
 * The scheme in force, resolved at render time.
 *
 * `useResolvedScheme()` is the reader's preference resolved against the OS, and
 * it is the same value `SchemePreferenceProvider` hands the design system as
 * `ThemeProvider`'s `scheme` — so Humbugg's own surfaces and the package's
 * components can never disagree about which scheme is in force. It used to read
 * `useColorScheme()` here directly, which is exactly the seam an in-app switch
 * could not reach.
 */
export function useTheme(): Theme {
  return themes[useResolvedScheme()];
}

/** The same records without a hook — for tests, and for module-scope reads. */
export function themeFor(scheme: Scheme): Theme {
  return themes[scheme];
}

/**
 * A component's own `StyleSheet`, built once per scheme rather than once.
 *
 * Local sheets used to close over the single `brand` object at module load,
 * which is exactly what could not follow the OS. Wrap the factory in this and
 * call it with the theme from `useTheme()`:
 *
 * ```ts
 * const local = scopedStyles((t) => ({ row: { borderColor: t.brand.line } }));
 * // …then, in the component: const styles = local(theme);
 * ```
 *
 * It is deliberately not a hook: a caller already holds the theme, and keeping
 * it a plain function means a sheet can be built for a scheme in a test.
 */
export function scopedStyles<T extends StyleSheet.NamedStyles<T>>(
  factory: (theme: Theme) => T & StyleSheet.NamedStyles<T>,
): (theme: Theme) => T {
  const built = new Map<Scheme, T>();
  return (theme) => {
    let sheet = built.get(theme.scheme);
    if (!sheet) {
      sheet = StyleSheet.create(factory(theme));
      built.set(theme.scheme, sheet);
    }
    return sheet;
  };
}
