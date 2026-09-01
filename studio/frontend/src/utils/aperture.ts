/**
 * Studio's mark, as geometry: a six-blade iris solved at any openness.
 *
 * **Why an aperture.** This app has one job — it makes pictures and it shows
 * them — and the diaphragm is the one piece of camera hardware whose *shape*
 * says "exposure" without a lens, a body or a shutter button around it. It is
 * also the only mark in this vocabulary that is already a loading indicator:
 * an iris that opens and closes is the same object doing the same thing, so
 * `ApertureSpinner` is not a second drawing of the logo, it is the logo with
 * `openness` moving.
 *
 * **The blades are computed, not a hand-drawn path.** A traced SVG can be shown
 * at exactly the openness it was traced at; every other state needs a second
 * trace, and a *tween* between two traces is not an iris — the straight edges
 * bend. `blades()` solves the real construction at any openness, so the header
 * mark, the favicon and every frame of the animation come out of one function
 * and cannot drift apart.
 *
 * **Pure, and deliberately outside `components/`.** `tool/render-mark.ts` runs
 * this file under bare node to write `public/aperture.svg`; a React import
 * anywhere in it would end that, and the favicon would become a second copy of
 * the drawing maintained by hand.
 */

// --- the construction ------------------------------------------------------
//
// Six identical blades on a circle of radius `R` about `(C, C)`. Blade `k` is
// bounded by two chords 60° apart and by the rim:
//
//   * its OWN chord, at distance `a` from the centre, which it sits outside of
//   * its NEIGHBOUR's chord, at distance `b`, which it sits inside of
//
// Both chords carry the same nominal distance `d`; the gap between adjacent
// blades is opened by pushing one out to `d + gap/2` and pulling the other in
// to `d - gap/2`. Doing it on both sides of the same line is what makes the gap
// a strip of CONSTANT width running from the opening to the rim, rather than a
// wedge that pinches shut at one end. Pushing both chords the same way — the
// first thing that suggests itself — moves the two blades' shared edge and
// opens nothing at all.
//
// The six chords at distance `a` are the sides of the hexagonal opening, so
// `openness` is really "how far off centre the blades' inner edges sit", and at
// `openness = 0` the blades close into a solid disc split six ways.

const C = 50;
const R = 48;
const BLADES = 6;
const STEP = 360 / BLADES;

/** Where a blade's own chord lands when the iris is wide open. */
const D_MAX = 0.58 * R;

/**
 * A quarter turn back, so the opening sits flat-topped with a point left and
 * right. The hexagon is symmetric enough that this is taste rather than
 * geometry — but it is the orientation every aperture diagram is drawn in, and
 * a mark rotated off it reads as slightly fallen over.
 */
const PHASE = -90;

const rad = (degrees: number) => (degrees * Math.PI) / 180;
const deg = (radians: number) => (radians * 180) / Math.PI;
const round = (n: number) => Math.round(n * 1000) / 1000;

function point(angle: number, radius: number): string {
  return `${round(C + radius * Math.cos(rad(angle)))} ${round(C + radius * Math.sin(rad(angle)))}`;
}

/**
 * The six blade paths at a given openness.
 *
 * `openness` runs 0 (shut) to 1 (wide). `gap` is the space between adjacent
 * blades in viewBox units — see `GAP_FOR` for why it is not a constant.
 *
 * Every path is `M … L … A … Z` with the same commands in the same order at
 * every openness, which is what lets the spinner rewrite `d` in place instead
 * of replacing elements sixty times a second.
 */
export function blades(openness: number, gap = 2.2): string[] {
  const d = D_MAX * Math.min(Math.max(openness, 0), 1);
  const a = d + gap / 2;
  const b = d - gap / 2;

  // Half-lengths of the two chords inside the circle. `b` may be negative at a
  // nearly-shut iris — the neighbour's edge has crossed the centre — which is
  // fine: `b * b` is what the chord length depends on, and `atan2` reads the
  // sign correctly on its own.
  const halfA = Math.sqrt(R * R - a * a);
  const halfB = Math.sqrt(R * R - b * b);

  // The hinge: where this blade's chord meets its neighbour's. Solving
  // `p · nOwn = a` and `p · nNeighbour = b` for two normals 60° apart gives a
  // point at this radius, this far round from the blade's own normal.
  const hingeR = Math.hypot(a, (a - 2 * b) / Math.sqrt(3));
  const hingeA = deg(Math.atan2((a - 2 * b) / Math.sqrt(3), a));

  const own = deg(Math.atan2(halfA, a));
  const neighbour = deg(Math.atan2(halfB, b));

  return Array.from({ length: BLADES }, (_, k) => {
    const m = PHASE + STEP * k;
    // Negated angles: the blades sweep anticlockwise, the handedness every
    // f-stop diagram draws. Mirroring with a transform would do the same thing
    // and would then have to be undone by anything measuring the paths.
    const hinge = point(m - hingeA, hingeR);
    const rimOwn = point(m - own, R);
    const rimNeighbour = point(m + STEP - neighbour, R);
    return `M${hinge}L${rimOwn}A${R} ${R} 0 0 1 ${rimNeighbour}Z`;
  });
}
