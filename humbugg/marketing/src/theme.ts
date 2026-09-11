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
import { useEffect, useState } from 'react';

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

// Every mounted `useThemePreference()` — the header's control AND the
// footer's mirror of it, see `components/ThemeToggle.tsx` — subscribes here,
// so a change made through either one is reflected by both immediately. The
// native `storage` event doesn't cover this: it fires for OTHER tabs, never
// the tab that made the write, so two instances on the SAME page would drift
// without a channel of their own.
type Listener = (preference: ThemePreference) => void;
const listeners = new Set<Listener>();

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
  listeners.forEach((listener) => listener(preference));
}

export type ThemeScheme = 'light' | 'dark';

/** What a preference paints right now — `system` resolved against the OS query. */
export function resolveThemeScheme(preference: ThemePreference): ThemeScheme {
  if (preference === 'system') return prefersDark() ? 'dark' : 'light';
  return preference;
}

/**
 * One preference, shared by every component that calls this — see the
 * `listeners` note above. Renders `system`/`light` on the first pass (server
 * AND client, so hydration never mismatches — the head script already painted
 * the real answer before React mounts) and corrects itself from
 * `localStorage` and the OS query in an effect.
 *
 * The third member is the scheme that preference currently paints. It is
 * what the control's icon shows — a visitor on "System" sees a moon, not a
 * monitor, because the moon is what is on screen — and it is why this hook
 * tracks the OS query rather than only re-painting on it: while the current
 * choice is "System", the head script's own listener stops the instant a
 * stored key exists, so once a visitor has chosen "System" in this tab
 * (rather than simply never having chosen anything), something still has to
 * react to the OS flipping without a reload — for as long as the choice
 * stays "System".
 */
export function useThemePreference(): [ThemePreference, (preference: ThemePreference) => void, ThemeScheme] {
  const [preference, setPreference] = useState<ThemePreference>('system');
  const [scheme, setScheme] = useState<ThemeScheme>('light');

  useEffect(() => {
    setPreference(getStoredThemePreference());
    listeners.add(setPreference);
    return () => {
      listeners.delete(setPreference);
    };
  }, []);

  useEffect(() => {
    setScheme(resolveThemeScheme(preference));
    if (preference !== 'system') return undefined;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      applyThemePreference('system');
      setScheme(resolveThemeScheme('system'));
    };
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [preference]);

  return [preference, setThemePreference, scheme];
}
