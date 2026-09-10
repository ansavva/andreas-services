// Humbugg's colours meet WCAG AA where Humbugg actually paints them (#138), in BOTH schemes.
//
// Contrast is the one accessibility property fully decidable from the palette, so it is checked
// here rather than left to a manual sweep — and it is checked against `brand-colors.json` itself,
// so editing a brand colour is what runs it. That file is also the source the marketing site's
// `styles.css` and the Cognito Managed Login document are kept in step with, which makes this the
// only place the rule needs to live.
//
// Only pairs the app really renders are listed. A matrix of every colour against every other would
// fail on combinations nothing draws, and the usual repair for that is to loosen the threshold.
import brandDark from './brand-colors.dark.json';
import brandLight from './brand-colors.json';

/**
 * Both schemes, checked against the same pairs.
 *
 * The pairs are the same because the app paints the same things; only the values
 * differ. Anything true of one palette and not the other is a bug in that
 * palette, not a reason for the dark scheme to own a shorter list.
 */
const palettes = { light: brandLight, dark: brandDark };
type SchemeName = keyof typeof palettes;

/** Relative luminance, per WCAG 2.2. */
function luminance(hex: string): number {
  const value = parseInt(hex.slice(1), 16);
  const channel = (byte: number) => {
    const unit = byte / 255;
    return unit <= 0.03928 ? unit / 12.92 : Math.pow((unit + 0.055) / 1.055, 2.4);
  };
  return (
    0.2126 * channel((value >> 16) & 255) +
    0.7152 * channel((value >> 8) & 255) +
    0.0722 * channel(value & 255)
  );
}

function contrast(foreground: string, background: string): number {
  const [a, b] = [luminance(foreground), luminance(background)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

type Role = keyof typeof brandLight;

/**
 * Foreground/background pairs the app draws, and where.
 *
 * The `where` is not decoration: when one of these fails the question is always "does the app
 * really do that?", and the answer belongs in the test rather than being rediscovered by grep.
 */
const TEXT_PAIRS: Array<[Role, Role, string]> = [
  ['ink', 'bg', 'body text on the page'],
  ['ink', 'card', 'body text in a card'],
  ['ink', 'surfaceAlt', 'body text in a panel and in a question bubble'],
  ['muted', 'bg', 'secondary text on the page'],
  ['muted', 'card', 'secondary text in a card'],
  // The design system's `Avatar.Fallback` paints `muted` initials on `surfaceAlt`, and
  // `styles.panel` and the "theirs" question bubble are `surfaceAlt` containers holding muted
  // text. This is the pair that was failing at 4.13 when the check was written.
  ['muted', 'surfaceAlt', 'avatar initials, and secondary text in a panel'],
  ['primaryText', 'primary', 'a primary button label'],
  ['primaryText', 'primaryHover', 'a primary button label, hovered'],
  ['primaryText', 'primaryActive', 'a primary button label, pressed'],
  ['primary', 'bg', 'a secondary button label'],
  ['primary', 'card', 'a secondary button label in a card'],
  // `styles.link` is 14px, so it is normal text and owes 4.5 rather than 3. It was failing at 3.77.
  ['accent', 'bg', 'a link'],
  ['accent', 'card', 'a link in a card'],
  ['accentHover', 'bg', 'a link, hovered'],
  ['accentHover', 'card', 'a link in a card, hovered'],
];

/**
 * 4.5:1 — WCAG 2.2 AA for normal text.
 *
 * Every text style in `theme/styles.ts` is under 18pt, and under 14pt bold, so none qualify for the
 * 3:1 large-text allowance. If a genuinely large style is ever added it gets its own list rather
 * than a lowered threshold here.
 */
describe.each(Object.keys(palettes) as SchemeName[])('%s', (scheme) => {
  const brand = palettes[scheme];
  describe.each(TEXT_PAIRS)('%s on %s', (foreground, background, where) => {
    it(`meets WCAG AA as ${where}`, () => {
      expect(
        Number(contrast(brand[foreground], brand[background]).toFixed(2)),
      ).toBeGreaterThanOrEqual(4.5);
    });
  });
});

/**
 * A hover state moves TOWARD the foreground, not merely away from its resting colour.
 *
 * This rule used to read "darker than", which was light-scheme reasoning wearing a general name:
 * on cream, moving toward the ink means going darker. On a dark page the same intent inverts —
 * a hover that goes darker sinks into the background and reads as the button going dead under the
 * finger. So the direction is per scheme; the rule is not.
 *
 * It matters more here than the ratios do: on native these are PRE-COMPUTED values rather than
 * live `color-mix()` blends (see `theme.ts`), so nothing derives them and nothing else would
 * notice one set the wrong way.
 */
describe.each(Object.keys(palettes) as SchemeName[])('%s', (scheme) => {
  const brand = palettes[scheme];
  const towardForeground = (state: Role, resting: Role) =>
    scheme === 'dark'
      ? expect(luminance(brand[state])).toBeGreaterThan(luminance(brand[resting]))
      : expect(luminance(brand[state])).toBeLessThan(luminance(brand[resting]));

  it.each([
    ['primaryHover', 'primary'],
    ['primaryActive', 'primaryHover'],
    ['accentHover', 'accent'],
  ] as Array<[Role, Role]>)('%s moves toward the foreground from %s', (state, resting) => {
    towardForeground(state, resting);
  });
});

/** The two files hold the same thirteen roles — a missing dark role is a silent default. */
it('states every light role in dark too', () => {
  expect(Object.keys(brandDark).sort()).toEqual(Object.keys(brandLight).sort());
});
