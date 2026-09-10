/**
 * The visitor's colour-scheme preference: `system` follows the OS, `light`/
 * `dark` are explicit and win over it. This is the ONLY thing the marketing
 * site keeps in `localStorage` — one key, written only for an explicit
 * choice; picking `system` removes it rather than writing `'system'`, so
 * "nothing stored" and "system" are the same state and the head script in
 * `app/root.tsx` (which runs before this module ever loads) only has two
 * branches to worry about.
 *
 * `app/root.tsx` re-implements the read half of this as an inline string —
 * it has to run as a blocking `<script>` in `<head>`, before hydration, so it
 * cannot import a module. Keep the two in step by hand if this key or its
 * values change.
 */
export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_STORAGE_KEY = 'humbugg:theme';

function safeRead(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // Safari private mode throws on `localStorage` access rather than
    // returning null — a preference that can't be remembered is not worth
    // failing the page over.
    return null;
  }
}

function safeWrite(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Same as above: functional-only, not required to work.
  }
}

function safeRemove(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Same as above.
  }
}

/** What's actually stored, normalized to a valid preference. */
export function getStoredThemePreference(): ThemePreference {
  const stored = safeRead(THEME_STORAGE_KEY);
  return stored === 'light' || stored === 'dark' ? stored : 'system';
}

function prefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/** Paints `data-theme` for a preference, resolving `system` against the OS query. */
export function applyThemePreference(preference: ThemePreference): void {
  const dark = preference === 'system' ? prefersDark() : preference === 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

/**
 * Records a preference (or clears it, for `system`) and paints it
 * immediately — no reload, no waiting on the next OS query.
 */
export function setThemePreference(preference: ThemePreference): void {
  if (preference === 'system') {
    safeRemove(THEME_STORAGE_KEY);
  } else {
    safeWrite(THEME_STORAGE_KEY, preference);
  }
  applyThemePreference(preference);
}
