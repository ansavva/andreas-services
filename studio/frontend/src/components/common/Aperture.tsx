import { useEffect, useRef } from "react";

import { blades } from "../../utils/aperture";

/**
 * The mark and the loading state, which are the same drawing.
 *
 * The construction itself is in `utils/aperture` — see that file for why it is
 * solved rather than traced, and for what a blade actually is. Everything here
 * is presentation: how big, how wide a gap at that size, and how the iris moves
 * while something is loading.
 */

// --- the mark --------------------------------------------------------------

type ApertureSize = "sm" | "md" | "lg" | "xl";

const SIZE_CLASS: Record<ApertureSize, string> = {
  sm: "size-4",
  md: "size-6",
  lg: "size-8",
  xl: "size-12",
};

/**
 * Optical sizing, because a gap is measured in viewBox units and *seen* in
 * device pixels. 2.2 units is a clean hairline on a 48px mark and about a third
 * of a pixel on a 16px one, where the blades silt up into a plain disc.
 * Widening the gap as the mark shrinks is what keeps six blades legible all the
 * way down — the difference between reading as an iris and reading as a circle.
 * Checked at all four sizes against a browser, not derived.
 */
const GAP_FOR: Record<ApertureSize, number> = { sm: 4.4, md: 3.2, lg: 2.6, xl: 2.2 };

interface MarkProps {
  /** 0 shut, 1 wide. */
  openness?: number;
  size?: ApertureSize;
  /** Replaces the size class entirely — same rule as `icons.tsx`. */
  className?: string;
}

/**
 * The static logo. `currentColor`, so it takes the ink of whatever it sits in
 * and needs no token of its own; `aria-hidden`, because it appears beside the
 * word *Studio* and a mark that announces itself next to its own wordmark is
 * read twice.
 */
export function ApertureMark({ openness = 1, size = "md", className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      className={className ?? `${SIZE_CLASS[size]} shrink-0`}
      fill="currentColor"
    >
      {blades(openness, GAP_FOR[size]).map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}

// --- the loading state -----------------------------------------------------

/** One full open-and-shut, in milliseconds. */
const PERIOD = 1900;

/**
 * How far the iris opens while loading — short of `1`, so the wide end of the
 * travel still reads as a blade position rather than as the logo standing
 * still. The shut end goes all the way to 0: a solid disc is the only frame in
 * the cycle that is unmistakably *closed*, and losing it costs the animation
 * its beat.
 */
const OPEN = 0.86;

/**
 * The shape of the cycle: shut → open → shut, eased at both ends and held for a
 * beat at each extreme.
 *
 * The hold is what makes it read as a mechanism. A pure sine cycles smoothly and
 * therefore looks like a pulse; a real iris snaps to a stop and sits there. The
 * two flat sixths of the period are that stop.
 */
function openness(phase: number): number {
  const HOLD = 1 / 6;
  const half = phase < 0.5 ? phase * 2 : (1 - phase) * 2;
  const eased = Math.min(Math.max((half - HOLD) / (1 - 2 * HOLD), 0), 1);
  return OPEN * (0.5 - Math.cos(Math.PI * eased) / 2);
}

interface SpinnerProps {
  size?: ApertureSize;
  /** The accessible name. Matches the design system's `Spinner` default. */
  label?: string;
  className?: string;
}

/**
 * The loading indicator: the mark, opening and closing.
 *
 * **A drop-in for the design system's `Spinner`** — same `size`/`label` props,
 * same `role="progressbar"` with no `aria-valuenow`, which is how ARIA spells
 * "indeterminate". The ring it replaces is a fine generic spinner; it is just
 * not studio's, and this app shows a loading state on nearly every route.
 *
 * **`d` is written straight to the DOM, not through state.** Sixty renders a
 * second of a component that only ever changes six attributes would put the
 * whole subtree through React's reconciler for nothing, and several of these
 * are on screen at once during a cold load.
 *
 * **`prefers-reduced-motion` gets a still mark, not a slower one.** The point of
 * the setting is that nothing loops; a gentler loop is still a loop.
 */
export function ApertureSpinner({ size = "md", label = "Loading", className }: SpinnerProps) {
  const paths = useRef<(SVGPathElement | null)[]>([]);
  const gap = GAP_FOR[size];

  useEffect(() => {
    // `matchMedia` is absent in some test environments; treat that as "motion
    // is fine" rather than letting the spinner throw on mount.
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (query?.matches) return;

    let frame = 0;
    let start = 0;
    const tick = (now: number) => {
      start ||= now;
      const next = blades(openness(((now - start) % PERIOD) / PERIOD), gap);
      paths.current.forEach((path, i) => {
        const d = next[i];
        if (path && d) path.setAttribute("d", d);
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [gap]);

  return (
    <span
      role="progressbar"
      aria-label={label}
      className={`inline-flex ${className ?? ""}`.trim()}
    >
      {/* Shut is the first frame of the cycle, so a spinner that never gets a
          frame — reduced motion, a suspended tab — rests on a shape the cycle
          actually passes through. */}
      <svg
        viewBox="0 0 100 100"
        aria-hidden="true"
        className={`${SIZE_CLASS[size]} shrink-0`}
        fill="currentColor"
      >
        {blades(0, gap).map((d, i) => (
          <path
            key={i}
            d={d}
            ref={(el) => {
              paths.current[i] = el;
            }}
          />
        ))}
      </svg>
    </span>
  );
}
