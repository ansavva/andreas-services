import { Toggle, ToggleGroup } from '@ansavva/design-system';
import type { ReactElement } from 'react';

import { useThemePreference, type ThemePreference } from '../theme';

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
 * Icon-only and `sm`-sized (three 32px squares) so it can sit beside
 * "Start a group" in the header without crowding it out; `className` is how
 * `Layout.tsx` places two of these — one in the header, one mirrored in the
 * footer for widths too narrow for the header copy — and hides each at the
 * width the other one owns. Both read the SAME preference, via
 * `useThemePreference`'s shared subscription (`theme.ts`), so a choice made
 * through whichever one is visible is what the other shows if the viewport
 * ever crosses the breakpoint without a reload.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [preference, setPreference] = useThemePreference();

  return (
    <ToggleGroup.Root
      aria-label="Theme"
      size="sm"
      className={className}
      value={[preference]}
      onValueChange={(next) => {
        // Outside `multiple` mode, ToggleGroup unpresses the already-pressed
        // member instead of leaving it pressed — right for an on/off toggle,
        // wrong for a three-way exclusive choice, where clicking the current
        // option must be a no-op rather than clearing the selection.
        const chosen = next[0];
        if (!chosen) return;
        setPreference(chosen as ThemePreference);
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
