import type { RunFeedRow } from "../../types";

/**
 * The feed's clock: relative times, elapsed counters and the day groups.
 *
 * Every function takes `now` rather than reading the clock, so a test can pin
 * it and a row can tick every second from one `useNow()` without each cell
 * calling `Date.now()` at a slightly different instant.
 */

const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** `12s ago`, `2m ago`, `1h ago`, `3d ago` — the feed's compact past tense. */
export function relativeTime(iso: string | null, now: number): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const gap = Math.max(0, now - then);
  if (gap < MINUTE) return `${Math.floor(gap / SECOND)}s ago`;
  if (gap < HOUR) return `${Math.floor(gap / MINUTE)}m ago`;
  if (gap < DAY) return `${Math.floor(gap / HOUR)}h ago`;
  return `${Math.floor(gap / DAY)}d ago`;
}

/** Seconds since `iso`, as `12s` / `1m 05s` — the counter on a run in flight. */
export function elapsedSince(iso: string | null, now: number): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.floor((now - then) / SECOND));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${String(seconds % 60).padStart(2, "0")}s`;
}

/** Midnight, local time, of the day `at` falls in. */
function startOfDay(at: number): number {
  const date = new Date(at);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

/**
 * The group heading for a day: `Today`, `Yesterday`, then the date.
 *
 * Local days, because "today" is a question about the person reading, not
 * about UTC — a run sent at 23:30 is today's run to whoever sent it.
 */
export function dayLabel(iso: string, now: number): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "Undated";
  const today = startOfDay(now);
  const day = startOfDay(then);
  if (day === today) return "Today";
  if (day === startOfDay(today - DAY)) return "Yesterday";
  const date = new Date(then);
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    ...(date.getFullYear() === new Date(now).getFullYear() ? {} : { year: "numeric" }),
  });
}

export interface DayGroup {
  label: string;
  rows: RunFeedRow[];
}

/**
 * Rows into day groups, in the order given — the feed asks newest first, so
 * the first group is the most recent day.
 *
 * Grouped on `created`, not `submitted`: a draft has no `submitted`, and a run
 * belongs to the day it was planned in either way.
 */
export function groupByDay(rows: RunFeedRow[], now: number): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const row of rows) {
    const label = dayLabel(row.created, now);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.rows.push(row);
    else groups.push({ label, rows: [row] });
  }
  return groups;
}

/** Whether a run has gone out and not come back. */
export function inFlight(status: RunFeedRow["status"]): boolean {
  return status === "pending" || status === "running";
}
