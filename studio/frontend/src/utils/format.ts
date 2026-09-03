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
 * A unit that reads better as a parenthetical suffix than as a capitalised
 * word — `lens_mm` is a measurement, not a word spelled "Mm".
 */
const UNIT_SUFFIXES = new Set(["mm", "cm", "kg", "ms", "px"]);

/** A segment that reads as an acronym rather than a word — an id or a url. */
const ACRONYMS = new Set(["id", "url", "fps"]);

function capitalise(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/**
 * A schema or profile key, as a label — `apparent_age` → `Apparent age`,
 * `lens_mm` → `Lens (mm)`, `run_id` → `Run ID`.
 *
 * One function rather than three call sites each guessing at the same
 * problem: `SchemaParams` used to show the raw key verbatim, `RunPlanEditor`
 * special-cased exactly one of them, and `ProfileForm`'s own `humanise` did
 * the plain case alone. A model's schema and a character's bible are both
 * snake_case for machines; a person reads sentence case with the odd
 * acronym or unit kept legible.
 */
export function humaniseKey(key: string): string {
  const words = key.split("_").filter(Boolean);
  if (words.length === 0) return key;

  if (words.length === 1 && ACRONYMS.has(words[0]!.toLowerCase())) {
    return words[0]!.toUpperCase();
  }

  const last = words[words.length - 1]!.toLowerCase();
  if (words.length > 1 && UNIT_SUFFIXES.has(last)) {
    return `${capitalise(words.slice(0, -1).join(" ").toLowerCase())} (${last})`;
  }

  return words
    .map((word, index) => {
      const lower = word.toLowerCase();
      if (ACRONYMS.has(lower)) return lower.toUpperCase();
      return index === 0 ? capitalise(lower) : lower;
    })
    .join(" ");
}

/**
 * The pipeline names run folders `<timestamp>_<slug>`, e.g.
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
