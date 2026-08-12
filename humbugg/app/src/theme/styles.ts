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
// the original). Static colours are safe here — see the note on `brand` in
// `theme.ts` for why.
import { StyleSheet } from 'react-native';

import { brand, fonts } from './theme';

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
export const blends = {
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
  /** `.assignment-label` — primaryText at 65%. */
  assignmentLabel: alpha(brand.primaryText, 65),
} as const;

export const styles = StyleSheet.create({
  // ── Page furniture ────────────────────────────────────────────────────────
  /** `min-h-screen bg-bg text-ink` */
  screen: { flex: 1, backgroundColor: brand.bg },
  /** `mx-auto max-w-7xl px-5 py-10 lg:px-8` */
  main: { width: '100%', maxWidth: 1280, alignSelf: 'center', paddingHorizontal: 20, paddingVertical: 40 },
  /** `border-b border-line/80 bg-bg/95` — the sticky header band. */
  header: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: alpha(brand.line, 80),
    backgroundColor: brand.bg,
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
  /** `font-heading text-5xl font-semibold leading-tight` */
  displayXl: { color: brand.ink, fontFamily: fonts.heading, fontSize: 48, lineHeight: 53 },
  /** `font-heading text-4xl font-semibold` */
  displayLg: { color: brand.ink, fontFamily: fonts.heading, fontSize: 36, lineHeight: 42 },
  /** `font-heading text-3xl font-semibold` */
  displayMd: { color: brand.ink, fontFamily: fonts.heading, fontSize: 30, lineHeight: 36 },
  /** `font-heading text-2xl font-semibold` */
  heading: { color: brand.ink, fontFamily: fonts.heading, fontSize: 24, lineHeight: 30 },
  /** `font-heading text-xl font-semibold` */
  headingSm: { color: brand.ink, fontFamily: fonts.heading, fontSize: 20, lineHeight: 26 },
  /** Body copy — Archivo at the browser default 16px. */
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
    borderRadius: 11.5, // .72rem
    borderWidth: 1,
    borderColor: alpha(brand.primaryText, 16), // the CSS inset ring
    backgroundColor: brand.primary,
    transform: [{ rotate: '-1deg' }],
    shadowColor: brand.primary,
    shadowOpacity: 0.18,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 5 },
    elevation: 3,
  },
  brandMarkText: { color: brand.primaryText, fontFamily: fonts.wordmark, fontSize: 32 },
  /** `.brand-mark-large` */
  brandMarkLarge: { width: 64, height: 64, borderRadius: 18.4 },
  brandMarkLargeText: { fontSize: 52 },
  /** `.brand-wordmark` */
  wordmark: {
    color: brand.primary,
    fontFamily: fonts.wordmark,
    fontSize: 37.6, // 2.35rem
    letterSpacing: -0.94, // -.025em
  },

  // ── Surfaces ──────────────────────────────────────────────────────────────
  /** `Card` from the web app's Layout: `rounded-2xl border border-line bg-card p-6 shadow-sm`. */
  card: {
    borderWidth: 1,
    borderColor: brand.line,
    borderRadius: 16,
    padding: 24,
    backgroundColor: brand.card,
    shadowColor: brand.ink,
    shadowOpacity: 0.05,
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
    borderRadius: 24,
    padding: 28,
    backgroundColor: brand.card,
    shadowColor: brand.ink,
    shadowOpacity: 0.13,
    shadowRadius: 70,
    shadowOffset: { width: 0, height: 24 },
    elevation: 8,
  },
  /** `rounded-xl bg-surface-alt p-5` — the inset panels in the organizer tools. */
  panel: { borderRadius: 12, backgroundColor: brand.surfaceAlt, padding: 20 },
  /** `.empty-panel` */
  emptyPanel: {
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: brand.line,
    borderRadius: 16,
    paddingVertical: 40,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  /** `.loading-panel` */
  loadingPanel: { minHeight: 320, alignItems: 'center', justifyContent: 'center', gap: 12 },

  // ── Status ────────────────────────────────────────────────────────────────
  /** `.status-message` */
  statusMessage: { marginTop: 16, borderRadius: 12, paddingVertical: 13, paddingHorizontal: 16 },
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
    borderRadius: 999,
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
    borderRadius: 999,
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
    borderRadius: 14,
    padding: 16,
  },
  groupRowActive: { borderColor: brand.primary },
  /** `.member-row` */
  memberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 13,
    borderRadius: 13,
    padding: 12,
    backgroundColor: brand.surfaceAlt,
  },
  /** `.avatar-chip` */
  avatarChip: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    backgroundColor: blends.avatarChip,
  },
  avatarChipText: { color: brand.primary, fontFamily: fonts.heading, fontSize: 15 },
  /** `.pair-chip` */
  pairChip: {
    borderRadius: 999,
    paddingVertical: 6,
    paddingHorizontal: 11,
    backgroundColor: brand.surfaceAlt,
  },
  pairChipText: { color: brand.ink, fontFamily: fonts.body, fontSize: 12 },
  /** `.group-meta span` */
  metaChip: {
    borderWidth: 1,
    borderColor: brand.line,
    borderRadius: 999,
    paddingVertical: 7,
    paddingHorizontal: 12,
    backgroundColor: brand.card,
  },
  /** `.group-heading` */
  groupHeading: { gap: 32, borderBottomWidth: 1, borderBottomColor: brand.line, paddingBottom: 32 },

  // ── The assignment reveal ─────────────────────────────────────────────────
  /** `.assignment-card` */
  assignmentCard: {
    borderRadius: 24,
    padding: 32,
    backgroundColor: brand.primary,
    shadowColor: brand.primary,
    shadowOpacity: 0.2,
    shadowRadius: 50,
    shadowOffset: { width: 0, height: 18 },
    elevation: 6,
  },
  /** `.assignment-label` */
  assignmentLabel: {
    marginBottom: 6,
    color: blends.assignmentLabel,
    fontFamily: fonts.bodyBold,
    fontSize: 11.5,
    letterSpacing: 1.38, // .12em
    textTransform: 'uppercase',
  },
  assignmentText: { color: brand.primaryText, fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },

  // ── Forms ─────────────────────────────────────────────────────────────────
  /** `.field-label` */
  fieldLabel: { gap: 7 },
  fieldLabelText: { color: brand.ink, fontFamily: fonts.bodySemibold, fontSize: 14 },
  /** `.nav-link` */
  navLink: {
    minHeight: 40,
    justifyContent: 'center',
    borderRadius: 8,
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
    borderRadius: 12,
    padding: 4,
    backgroundColor: brand.card,
    shadowColor: brand.ink,
    shadowOpacity: 0.15,
    shadowRadius: 15,
    shadowOffset: { width: 0, height: 10 },
    elevation: 8,
  },
  menuItem: { borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12 },
  menuItemText: { color: brand.ink, fontFamily: fonts.bodyMedium, fontSize: 14 },
  menuItemDangerText: { color: brand.danger },
});

/** Gaps the source expressed as `space-y-*` / `gap-*`, in one place. */
export const gap = { xs: 8, sm: 12, md: 16, lg: 20, xl: 28, xxl: 32 } as const;
