import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApertureMark, ApertureSpinner } from "./Aperture";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Pretend the viewer has asked for less motion — or has not. */
function reducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: reduce, addEventListener() {}, removeEventListener() {} })),
  );
}

function paths(): (string | null)[] {
  return Array.from(document.querySelectorAll("path"), (p) => p.getAttribute("d"));
}

/**
 * Long enough to be past the shut-and-hold the cycle opens on — roughly a sixth
 * of the period — so "nothing moved" means the animation is off rather than
 * that it has not started yet.
 */
const PAST_THE_HOLD = 320;

const settle = () =>
  new Promise((resolve) => setTimeout(() => requestAnimationFrame(resolve), PAST_THE_HOLD));

describe("the mark", () => {
  it("is hidden from the accessibility tree", () => {
    const { container } = render(<ApertureMark />);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("draws six blades", () => {
    const { container } = render(<ApertureMark />);
    expect(container.querySelectorAll("path")).toHaveLength(6);
  });
});

describe("the loading state", () => {
  /**
   * The contract it inherits from the design system's `Spinner`, which it
   * replaced at sixteen call sites: `progressbar` with a name and no
   * `aria-valuenow`, which is how ARIA spells "indeterminate".
   */
  it("announces itself as an indeterminate progressbar with a name", () => {
    reducedMotion(false);
    render(<ApertureSpinner label="Loading runs" />);

    const bar = screen.getByRole("progressbar", { name: "Loading runs" });
    expect(bar.getAttribute("aria-valuenow")).toBeNull();
  });

  it("moves the blades", async () => {
    reducedMotion(false);
    render(<ApertureSpinner />);
    const before = paths();

    await settle();

    expect(paths()).not.toEqual(before);
  });

  /**
   * A still mark, not a slower loop. The point of the setting is that nothing
   * repeats, and a gentle repeat is still a repeat.
   */
  it("holds still when the viewer has asked for less motion", async () => {
    reducedMotion(true);
    render(<ApertureSpinner />);
    const before = paths();

    await settle();

    expect(paths()).toEqual(before);
  });
});
