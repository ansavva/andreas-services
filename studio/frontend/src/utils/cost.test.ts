import { describe, expect, it } from "vitest";

import { formatCost } from "./cost";

/**
 * **This crashed the run page in production-shaped data, live, on the first real
 * generation**, and the stubbed screenshot that preceded it could not have caught
 * it: the stub had `cost: null`, which is the one shape that worked.
 *
 * Two call sites each did `cost.currency + cost.amount.toFixed(3)` on the
 * assumption that a `cost` object carries a number. True only of runs closed by
 * the CLI, which wrote a price. A run closed by the provider's callback carries
 * no price at all, because Replicate's response has no money in it.
 */
describe("what a run cost, in words", () => {
  it("shows a real price for a run closed before the callback existed", () => {
    expect(formatCost({ currency: "USD", amount: 0.032 })).toBe("USD 0.032");
  });

  it("shows model time when the provider reported no price", () => {
    /** The shape every callback-closed run has. */
    expect(
      formatCost({ currency: null, amount: null, predict_time: 98.207 }),
    ).toBe("98.2s of model time");
  });

  it("does not throw on a cost object with a null amount", () => {
    /** The regression itself: `Cannot read properties of null (reading 'toFixed')`. */
    expect(() => formatCost({ currency: null, amount: null })).not.toThrow();
    expect(formatCost({ currency: null, amount: null })).toBe("—");
  });

  it("says nothing for a run that never reached the provider", () => {
    // "—" is the one sentinel now: the run list and the run page used to
    // disagree here, and a caller can still ask for its own by name.
    expect(formatCost(null)).toBe("—");
    expect(formatCost(null, "not reported")).toBe("not reported");
  });

  it("keeps a zero price rather than reading it as absent", () => {
    /** `0` is falsy and is a real answer — a free generation is not an unknown one. */
    expect(formatCost({ currency: "USD", amount: 0 })).toBe("USD 0.000");
  });
});
