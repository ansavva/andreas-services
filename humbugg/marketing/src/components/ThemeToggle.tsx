import { Toggle, ToggleGroup } from '@ansavva/design-system';
import { useEffect, useState, type ReactElement } from 'react';

import { applyThemePreference, getStoredThemePreference, setThemePreference, type ThemePreference } from '../theme';

const OPTIONS: ReadonlyArray<{ value: ThemePreference; label: string; icon: ReactElement }> = [
  {
    value: 'system',
    label: 'System',
    icon: (
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="size-4">
        <rect x="2.5" y="3.5" width="15" height="10" rx="1.5" />
        <path d="M7 17h6M10 13.5V17" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    value: 'light',
    label: 'Light',
    icon: (
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="size-4">
        <circle cx="10" cy="10" r="3.5" />
        <path
          d="M10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1 4.7 4.7"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    value: 'dark',
    label: 'Dark',
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" className="size-4">
        <path d="M17 11.5A7.5 7.5 0 0 1 8.5 3a7.5 7.5 0 1 0 8.5 8.5Z" />
      </svg>
    ),
  },
];

/**
 * The marketing site's light/dark switch — independent of the product app,
 * which follows the OS with no override (see `app/root.tsx`).
 *
 * Renders `system` on the first pass, on both server and client, and
 * corrects from `localStorage` in an effect: the head script already painted
 * `data-theme` from the real preference before this component ever mounts,
 * so the only risk here is a hydration MISMATCH (server markup says one
 * thing, client render says another), not a flash — reading `localStorage`
 * during render would fix that risk by reintroducing it on every future SSR
 * framework that diffs the client's first render against the server's.
 */
export function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>('system');

  useEffect(() => {
    setPreference(getStoredThemePreference());
  }, []);

  // While the visible choice is "System", keep painting the OS's live
  // answer — the head script's own `change` listener stops the instant a
  // stored key exists, so once a visitor has chosen "System" in this tab
  // (rather than simply never having chosen anything) something still has
  // to react to the OS changing without a reload. This effect is that
  // something, for as long as the choice stays "System".
  useEffect(() => {
    if (preference !== 'system') return undefined;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => applyThemePreference('system');
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [preference]);

  return (
    <ToggleGroup.Root
      aria-label="Theme"
      size="sm"
      value={[preference]}
      onValueChange={(next) => {
        // Outside `multiple` mode, ToggleGroup unpresses the already-pressed
        // member instead of leaving it pressed — right for an on/off toggle,
        // wrong for a three-way exclusive choice, where clicking the current
        // option must be a no-op rather than clearing the selection.
        const chosen = next[0];
        if (!chosen) return;
        setPreference(chosen as ThemePreference);
        setThemePreference(chosen as ThemePreference);
      }}
    >
      {OPTIONS.map((option) => (
        <Toggle key={option.value} value={option.value} iconOnly label={option.label}>
          {option.icon}
        </Toggle>
      ))}
    </ToggleGroup.Root>
  );
}
