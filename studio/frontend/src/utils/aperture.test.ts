import { describe, expect, it } from "vitest";

import { blades } from "./aperture";

/**
 * The mark is solved rather than drawn, so what is worth pinning is not what
 * the path data says — it is the two properties that make the animation
 * possible at all, and the one that makes it look like an iris.
 */

/** Every number in a path, in order. */
function numbers(d: string): number[] {
  return (d.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
}

/** The commands, stripped of their operands. */
function shape(d: string): string {
  return (d.match(/[A-Z]/g) ?? []).join("");
}

describe("the aperture's geometry", () => {
  it("draws six blades at every openness", () => {
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      expect(blades(t)).toHaveLength(6);
    }
  });

  /**
   * The regression this guards is the whole animation. `ApertureSpinner`
   * rewrites `d` on six existing `<path>` elements sixty times a second; a
   * frame whose commands differ from the last one would not tween, it would
   * jump — and a frame with a different NUMBER of commands would leave the
   * paths mismatched with no error anywhere.
   */
  it("keeps the same commands and the same operand count at every openness", () => {
    const first = blades(0);
    for (const t of [0.01, 0.3, 0.5, 0.99, 1]) {
      blades(t).forEach((d, i) => {
        expect(shape(d)).toBe(shape(first[i]!));
        expect(numbers(d)).toHaveLength(numbers(first[i]!).length);
      });
    }
  });

  it("is stable — the same openness gives the same path", () => {
    expect(blades(0.5)).toEqual(blades(0.5));
  });

  it("clamps rather than inverting outside 0…1", () => {
    expect(blades(-1)).toEqual(blades(0));
    expect(blades(2)).toEqual(blades(1));
  });

  /**
   * The opening widens monotonically. Measured through the hinge — the first
   * point of each path is where a blade meets its neighbour, which is a corner
   * of the hexagonal opening — because that is the vertex a reader actually
   * sees move.
   */
  it("opens as `openness` rises", () => {
    const hinge = (t: number) => {
      const [x, y] = numbers(blades(t)[0]!);
      return Math.hypot(x! - 50, y! - 50);
    };
    const radii = [0, 0.25, 0.5, 0.75, 1].map(hinge);
    for (let i = 1; i < radii.length; i++) {
      expect(radii[i]!).toBeGreaterThan(radii[i - 1]!);
    }
  });

  /** Shut is a solid disc split six ways: the hinge sits all but on the centre. */
  it("shuts to the centre", () => {
    const [x, y] = numbers(blades(0)[0]!);
    expect(Math.hypot(x! - 50, y! - 50)).toBeLessThan(4);
  });

  /**
   * A wider gap eats into the blades from both sides, so the opening a given
   * openness leaves is larger. This is what `GAP_FOR` relies on to keep a 16px
   * spinner from silting up into a disc.
   */
  it("widens the opening when the gap widens", () => {
    const hinge = (gap: number) => {
      const [x, y] = numbers(blades(0.6, gap)[0]!);
      return Math.hypot(x! - 50, y! - 50);
    };
    expect(hinge(4.4)).toBeGreaterThan(hinge(2.2));
  });

  it("stays inside the viewBox", () => {
    for (const t of [0, 0.5, 1]) {
      for (const d of blades(t, 5)) {
        for (const n of numbers(d)) {
          expect(n).toBeGreaterThanOrEqual(0);
          expect(n).toBeLessThanOrEqual(100);
        }
      }
    }
  });
});
