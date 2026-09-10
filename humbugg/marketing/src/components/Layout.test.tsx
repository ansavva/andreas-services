import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LEGAL_LINKS } from '../config/policies';
import { APP_ORIGIN } from '../config/site';
import { THEME_STORAGE_KEY } from '../theme';
import { Shell, SiteFooter } from './Layout';

/**
 * jsdom implements neither `matchMedia` nor a live-updating one, so every
 * test that mounts `Shell` (and therefore `ThemeToggle`) needs a stand-in —
 * `matches` is what "system" resolves to, and the returned object is what
 * the toggle's effect attaches its OS-change listener to.
 */
function stubMatchMedia(matches: boolean) {
  const query = {
    matches,
    media: '(prefers-color-scheme: dark)',
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue(query as unknown as MediaQueryList),
  );
  return query;
}

function renderShell() {
  return render(
    <MemoryRouter>
      <Shell>
        <p>page body</p>
      </Shell>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // "System" resolving to light unless a test asks otherwise — matches the
  // OS default most readers of a failing assertion would expect.
  stubMatchMedia(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe('Shell', () => {
  it('links the header actions to the product app, cross-origin', () => {
    renderShell();
    // The product lives on another origin: these must be absolute anchors, never
    // react-router links that would resolve as marketing routes.
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', `${APP_ORIGIN}/login`);
    expect(screen.getByRole('link', { name: 'Start a group' })).toHaveAttribute('href', `${APP_ORIGIN}/login`);
  });

  it('brands home and renders the page body', () => {
    renderShell();
    expect(screen.getByRole('link', { name: 'Humbugg home' })).toHaveAttribute('href', '/');
    expect(screen.getByText('page body')).toBeInTheDocument();
  });

  it('footers every published legal document', () => {
    renderShell();
    const footer = within(screen.getByRole('contentinfo'));
    for (const link of LEGAL_LINKS) {
      expect(footer.getByRole('link', { name: link.label })).toHaveAttribute('href', link.to);
    }
  });
});

/**
 * The pricing page is reachable from every width.
 *
 * It shipped behind `hidden sm:inline-flex`, which meant that below 640px the header link was gone
 * and the footer carried only policy links — so on a phone there was no path to /pricing at all.
 * A class name cannot be caught by a render test that only counts links, so this asserts the
 * absence of the class as well as the presence of the link.
 */
describe('reaching the pricing page', () => {
  it('links to pricing from the header, at every width', () => {
    render(
      <MemoryRouter>
        <Shell>content</Shell>
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link', { name: 'Pricing' });
    expect(links.length).toBeGreaterThanOrEqual(1);
    // The header link specifically — the one that was hidden.
    const header = links.find((link) => link.className.includes('nav-link'));
    expect(header).toBeDefined();
    expect(header!.className).not.toContain('hidden');
  });

  it('links to pricing from the footer too, so the header is not the only path', () => {
    render(
      <MemoryRouter>
        <SiteFooter />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Pricing' })).toHaveAttribute('href', '/pricing');
  });
});

/**
 * The header hides its copy below `sm` (three icons don't fit beside "Start a
 * group" at 390px — measured, see the comment in `Shell`), so it is mirrored
 * in the footer the same way Pricing is: two elements with the same
 * accessible name, one of them a `hidden` class away from view at any given
 * width. `within(header)` picks the interactive one out for the tests below;
 * a separate test covers that the footer's copy is never left stale.
 */
describe('the theme control', () => {
  function headerGroup() {
    return within(within(screen.getByRole('banner')).getByRole('group', { name: 'Theme' }));
  }
  function footerGroup() {
    return within(within(screen.getByRole('contentinfo')).getByRole('group', { name: 'Theme' }));
  }

  it('renders in both the header and the footer, each named "Theme"', () => {
    renderShell();
    expect(screen.getAllByRole('group', { name: 'Theme' })).toHaveLength(2);
  });

  it('hides the header copy below `sm` and the footer copy at `sm` and up — never both at once', () => {
    renderShell();
    const header = within(screen.getByRole('banner')).getByRole('group', { name: 'Theme' });
    const footer = within(screen.getByRole('contentinfo')).getByRole('group', { name: 'Theme' });
    const headerClasses = header.className.split(/\s+/);
    const footerClasses = footer.className.split(/\s+/);
    expect(headerClasses).toContain('hidden');
    expect(headerClasses).toContain('sm:inline-flex');
    // The footer copy must NOT be unconditionally hidden — only `sm:hidden`,
    // i.e. hidden from the width the header copy takes back over.
    expect(footerClasses).not.toContain('hidden');
    expect(footerClasses).toContain('sm:hidden');
  });

  it('announces which option is current', () => {
    renderShell();
    const group = headerGroup();
    // Uncontroversial default: no stored key, so "System" is pressed and the
    // other two are not — this is the state a screen reader announces per
    // option via `aria-pressed`.
    expect(group.getByRole('button', { name: 'System' })).toHaveAttribute('aria-pressed', 'true');
    expect(group.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'false');
    expect(group.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('choosing Dark sets data-theme and writes localStorage', () => {
    renderShell();
    const group = headerGroup();
    fireEvent.click(group.getByRole('button', { name: 'Dark' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(group.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('choosing Light sets data-theme and writes localStorage', () => {
    renderShell();
    const group = headerGroup();
    fireEvent.click(group.getByRole('button', { name: 'Light' }));
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('choosing System removes the stored key and re-reads the OS query', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    stubMatchMedia(false); // OS says light
    renderShell();
    const group = headerGroup();

    // Starts from the stored explicit choice.
    expect(group.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(group.getByRole('button', { name: 'System' }));

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe('light'); // the OS query, not the old choice
    expect(group.getByRole('button', { name: 'System' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps the footer copy in step with a choice made in the header, without a remount', () => {
    renderShell();
    fireEvent.click(headerGroup().getByRole('button', { name: 'Dark' }));
    // Both mount independently (see `theme.ts`'s `useThemePreference`); this is
    // the subscription that is supposed to stop them drifting apart.
    expect(footerGroup().getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
    expect(footerGroup().getByRole('button', { name: 'System' })).toHaveAttribute('aria-pressed', 'false');
  });
});
