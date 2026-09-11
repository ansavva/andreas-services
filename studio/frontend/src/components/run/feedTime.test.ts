import { describe, expect, it } from "vitest";

import type { RunFeedRow } from "../../types";
import { dayLabel, elapsedSince, groupByDay, relativeTime } from "./feedTime";

const NOW = new Date("2026-09-04T15:00:00").getTime();
const at = (iso: string) => new Date(iso).toISOString();

describe("relativeTime", () => {
  it("counts in the largest unit that fits", () => {
    expect(relativeTime(at("2026-09-04T14:59:48"), NOW)).toBe("12s ago");
    expect(relativeTime(at("2026-09-04T14:58:00"), NOW)).toBe("2m ago");
    expect(relativeTime(at("2026-09-04T13:30:00"), NOW)).toBe("1h ago");
    expect(relativeTime(at("2026-09-01T15:00:00"), NOW)).toBe("3d ago");
    expect(relativeTime(null, NOW)).toBe("");
  });
});

describe("elapsedSince", () => {
  it("reads as seconds, then minutes and seconds", () => {
    expect(elapsedSince(at("2026-09-04T14:59:48"), NOW)).toBe("12s");
    expect(elapsedSince(at("2026-09-04T14:58:55"), NOW)).toBe("1m 05s");
    expect(elapsedSince(null, NOW)).toBe("");
  });
});

describe("dayLabel", () => {
  it("says Today and Yesterday in local days, then the date", () => {
    expect(dayLabel(at("2026-09-04T00:30:00"), NOW)).toBe("Today");
    expect(dayLabel(at("2026-09-03T23:30:00"), NOW)).toBe("Yesterday");
    expect(dayLabel(at("2026-08-30T12:00:00"), NOW)).toMatch(/Aug 30/);
    // A different year says which.
    expect(dayLabel(at("2025-12-24T12:00:00"), NOW)).toMatch(/2025/);
  });
});

describe("groupByDay", () => {
  it("keeps the order given and groups on the run's created day", () => {
    const row = (id: string, created: string) =>
      ({ id, created, status: "succeeded" }) as RunFeedRow;
    const groups = groupByDay(
      [
        row("a", at("2026-09-04T14:00:00")),
        row("b", at("2026-09-04T09:00:00")),
        row("c", at("2026-09-03T20:00:00")),
        row("d", at("2026-08-30T20:00:00")),
      ],
      NOW,
    );
    expect(groups.map((g) => [g.label, g.rows.map((r) => r.id)])).toEqual([
      ["Today", ["a", "b"]],
      ["Yesterday", ["c"]],
      [dayLabel(at("2026-08-30T20:00:00"), NOW), ["d"]],
    ]);
  });
});
