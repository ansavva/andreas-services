export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * The pipeline names run folders `<timestamp>_<name>`, e.g.
 * `2026-08-15_01-00-30_pullup-originals`. Splitting that back apart lets a run
 * read as a date and a name instead of one long token — and anything that does
 * not match the shape is left exactly as it is.
 */
export function describeFolder(name: string): { title: string; subtitle?: string } {
  const match = /^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_(.+)$/.exec(name);
  if (!match) return { title: name };

  const [, day, time, slug] = match;
  return { title: slug!, subtitle: `${day} ${time!.replace(/-/g, ":")}` };
}

/** Pretty-print JSON for the read-only viewer; leave anything else untouched. */
export function formatTextContent(content: string, language: string): string {
  if (language !== "json") return content;
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    // A truncated file is not valid JSON. Showing the raw bytes beats showing
    // an error for a viewer whose whole job is "let me look at this".
    return content;
  }
}
