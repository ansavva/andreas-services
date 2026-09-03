/**
 * The one fill every control floating over a media frame wears.
 *
 * **Was three copies of the same string literal.** `MediaPlayer`,
 * `PlayerTransport` and `ObjectActions`' media-variant controls each typed
 * `text-neutral-12 hover:bg-neutral-a5 active:bg-neutral-a6` by hand, which is
 * both the duplication and the raw-ramp violation this file exists to end —
 * `chrome-ink`/`chrome-hover`/`chrome-active` are `styles/app.css`'s semantic
 * names for exactly these three steps, so the class string says what the
 * paint is FOR rather than which rung of the ramp it happens to sit on.
 *
 * `touch-target` (#596) is folded in here too: every caller is a `size="sm"`
 * icon control over media — the exact case a finger is wider than the box.
 */
export const CHROME_BUTTON = "touch-target text-chrome-ink hover:bg-chrome-hover active:bg-chrome-active";
