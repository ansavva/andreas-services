import { Dropdown, iconButtonClass } from '@ansavva/design-system';
import { useState, type ReactElement } from 'react';

import { useThemePreference, type ThemePreference, type ThemeScheme } from '../theme';

const ICONS: Record<'system' | ThemeScheme, ReactElement> = {
  system: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="size-5">
      <rect x="2.5" y="3.5" width="15" height="10" rx="1.5" />
      <path d="M7 17h6M10 13.5V17" strokeLinecap="round" />
    </svg>
  ),
  light: (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="size-5">
      <circle cx="10" cy="10" r="3.5" />
      <path
        d="M10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1 4.7 4.7"
        strokeLinecap="round"
      />
    </svg>
  ),
  dark: (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" className="size-5">
      <path d="M17 11.5A7.5 7.5 0 0 1 8.5 3a7.5 7.5 0 1 0 8.5 8.5Z" />
    </svg>
  ),
};

const OPTIONS: ReadonlyArray<{ value: ThemePreference; label: string }> = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

/**
 * The marketing site's light/dark switch — independent of the product app,
 * which follows the OS with no override (see `app/root.tsx`).
 *
 * One icon button that opens a three-way menu, rather than three toggles in
 * a row: it sits at the head of the nav beside "Pricing", and one 44px square
 * is what fits there at 390px where three did not. The glyph on the button is
 * the scheme in EFFECT (sun or moon), not the stored preference — a visitor
 * on "System" is looking at a light or a dark page, and a monitor icon would
 * tell them nothing about which. The menu is where "System" is a choice, and
 * where the current one is marked.
 *
 * `className` is how `Layout.tsx` places two of these — one in the header,
 * one mirrored in the footer for widths too narrow for the header copy — and
 * hides each at the width the other one owns. Both read the SAME preference,
 * via `useThemePreference`'s shared subscription (`theme.ts`), so a choice
 * made through whichever one is visible is what the other shows if the
 * viewport ever crosses the breakpoint without a reload.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [preference, setPreference, scheme] = useThemePreference();
  const [open, setOpen] = useState(false);

  return (
    <div className={className}>
      <Dropdown.Root open={open} onOpenChange={setOpen}>
        <Dropdown.Trigger
          aria-label="Theme"
          title="Theme"
          // What the glyph shows, readable by a test — an SVG path is not.
          data-scheme={scheme}
          className={iconButtonClass({ intent: 'ghost', size: 'md', pressed: open })}
        >
          {ICONS[scheme]}
        </Dropdown.Trigger>
        <Dropdown.Content>
          {OPTIONS.map((option) => (
            <Dropdown.Item
              key={option.value}
              // `aria-current` rather than `aria-checked`: the design system's
              // menu walks `[role="menuitem"]` for its arrow keys, so the
              // radio role that `aria-checked` belongs to would fall out of
              // the keyboard order.
              aria-current={option.value === preference ? 'true' : undefined}
              onSelect={() => setPreference(option.value)}
              className="gap-3"
            >
              <span className="text-muted">{ICONS[option.value]}</span>
              <span className="grow">{option.label}</span>
              {option.value === preference && (
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className="size-4 text-primary">
                  <path d="m4.5 10.5 3.5 3.5 7.5-8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </Dropdown.Item>
          ))}
        </Dropdown.Content>
      </Dropdown.Root>
    </div>
  );
}
