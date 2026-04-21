/**
 * Format an ISO date string (YYYY-MM-DD) into a human-readable form.
 */
export function formatDate(dateStr: string): string {
  if (!dateStr) return "";
  try {
    const [year, month, day] = dateStr.split("-").map(Number);
    const d = new Date(year, month - 1, day);
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

/**
 * Return true when the event's date is today or in the future.
 */
export function isUpcoming(dateStr: string): boolean {
  if (!dateStr) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(year, month - 1, day) >= today;
}

/**
 * Truncate a string to maxLen characters, appending "…" if truncated.
 */
export function truncate(text: string, maxLen = 160): string {
  if (!text || text.length <= maxLen) return text ?? "";
  return text.slice(0, maxLen).trimEnd() + "…";
}

/**
 * Extract the bare hostname from a URL for display purposes.
 */
export function displayUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
