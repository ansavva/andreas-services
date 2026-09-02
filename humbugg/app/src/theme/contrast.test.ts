// Humbugg's colours meet WCAG AA where Humbugg actually paints them (#138).
//
// Contrast is the one accessibility property fully decidable from the palette, so it is checked
// here rather than left to a manual sweep — and it is checked against `brand-colors.json` itself,
// so editing a brand colour is what runs it. That file is also the source the marketing site's
// `styles.css` and the Cognito Managed Login document are kept in step with, which makes this the
// only place the rule needs to live.
//
// Only pairs the app really renders are listed. A matrix of every colour against every other would
// fail on combinations nothing draws, and the usual repair for that is to loosen the threshold.
import brand from './brand-colors.json';

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

type Role = keyof typeof brand;

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
describe.each(TEXT_PAIRS)('%s on %s', (foreground, background, where) => {
  it(`meets WCAG AA as ${where}`, () => {
    expect(Number(contrast(brand[foreground], brand[background]).toFixed(2))).toBeGreaterThanOrEqual(
      4.5,
    );
  });
});

/**
 * A hover state is darker than its resting colour, not merely different.
 *
 * On native these are pre-computed values rather than live `color-mix()` blends (see `theme.ts`),
 * so nothing derives them and nothing else would notice one being set lighter — which reads as the
 * button going pale under the finger.
 */
it.each([
  ['primaryHover', 'primary'],
  ['primaryActive', 'primaryHover'],
  ['accentHover', 'accent'],
] as Array<[Role, Role]>)('%s is darker than %s', (state, resting) => {
  expect(luminance(brand[state])).toBeLessThan(luminance(brand[resting]));
});
