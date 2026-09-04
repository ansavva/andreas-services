import { useEffect, useState } from "react";

/**
 * The time, re-read on an interval while `ticking`, and frozen otherwise.
 *
 * One clock per feed rather than one per row: every elapsed counter and every
 * "12s ago" reads the same instant, and a feed with nothing in flight
 * re-renders on no timer at all. Stopping when `ticking` goes false is what
 * keeps a finished feed still.
 */
export function useNow(ticking: boolean, everyMs = 1_000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!ticking) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(id);
  }, [everyMs, ticking]);

  return now;
}
