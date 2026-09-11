import type { RunCost } from "../types";

/**
 * What a run cost, in words. **One formatter, because there were two call sites
 * and they both got it wrong the same way.**
 *
 * `RunPage` and `RunsTable` each rendered `cost.currency + cost.amount.toFixed(3)`
 * on the assumption that a `cost` object always carries a number. That held only
 * while runs were closed by the CLI, which wrote a price. A run closed by the
 * provider's callback carries `{amount: null, currency: null, predict_time: N}` —
 * because Replicate's response has no money in it, and inventing an amount would
 * be this service making a number up — and both pages threw
 * `Cannot read properties of null` on the first real generation.
 *
 * Three cases, in the order they are true:
 *
 *   * a real price, on a run closed before the callback existed;
 *   * seconds of model time, which is what the provider does report;
 *   * nothing, which is honest for a run that never reached the provider.
 */
export function formatCost(cost: RunCost | null, empty = "—"): string {
  if (!cost) return empty;
  if (typeof cost.amount === "number") {
    return `${cost.currency ?? ""} ${cost.amount.toFixed(3)}`.trim();
  }
  if (typeof cost.predict_time === "number") {
    return `${cost.predict_time.toFixed(1)}s of model time`;
  }
  return empty;
}
