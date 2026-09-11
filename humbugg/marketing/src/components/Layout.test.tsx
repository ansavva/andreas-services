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
 * The header hides its copy below `sm` (one 44px square is still one too
 * many beside "Start a group" at 390px — measured, see the comment in
 * `Shell`), so it is mirrored in the footer the same way Pricing is: two
 * buttons with the same accessible name, one of them a `hidden` class away
 * from view at any given width. `within(header)` picks the interactive one
 * out for the tests below; a separate test covers that the footer's copy is
 * never left stale.
 *
 * The control is a menu button: the icon on it is the scheme in EFFECT, and
 * the three-way choice lives in the menu it opens. `aria-current` marks the
 * stored preference there — not `aria-pressed`, which belongs to a toggle and
 * is what the previous three-button version announced.
 */
describe('the theme control', () => {
  function headerButton() {
    return within(screen.getByRole('banner')).getByRole('button', { name: 'Theme' });
  }
  function footerButton() {
    return within(screen.getByRole('contentinfo')).getByRole('button', { name: 'Theme' });
  }
  /** Opens the header's menu and returns its items by name. */
  function openHeaderMenu() {
    fireEvent.click(headerButton());
    const menu = within(screen.getByRole('menu', { name: 'Theme' }));
    return {
      item: (name: 'System' | 'Light' | 'Dark') => menu.getByRole('menuitem', { name }),
    };
  }

  it('renders in both the header and the footer, each named "Theme"', () => {
    renderShell();
    expect(screen.getAllByRole('button', { name: 'Theme' })).toHaveLength(2);
  });

  it('hides the header copy below `sm` and the footer copy at `sm` and up — never both at once', () => {
    renderShell();
    // The `hidden`/`sm:` classes sit on the wrapper the component takes
    // `className` for, one level above the menu's own positioning root.
    const header = headerButton().closest('[class*="sm:"]')!;
    const footer = footerButton().closest('[class*="sm:"]')!;
    const headerClasses = header.className.split(/\s+/);
    const footerClasses = footer.className.split(/\s+/);
    expect(headerClasses).toContain('hidden');
    expect(headerClasses).toContain('sm:inline-flex');
    // The footer copy must NOT be unconditionally hidden — only `sm:hidden`,
    // i.e. hidden from the width the header copy takes back over.
    expect(footerClasses).not.toContain('hidden');
    expect(footerClasses).toContain('sm:hidden');
  });

  it('sits first in the header nav, left of the text actions', () => {
    renderShell();
    const nav = screen.getByRole('navigation', { name: 'Primary navigation' });
    expect(nav.firstElementChild!.contains(headerButton())).toBe(true);
  });

  it('is a menu button that opens a three-way choice, closed until pressed', () => {
    renderShell();
    expect(headerButton()).toHaveAttribute('aria-haspopup', 'menu');
    expect(headerButton()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    const { item } = openHeaderMenu();
    expect(headerButton()).toHaveAttribute('aria-expanded', 'true');
    expect(item('System')).toBeInTheDocument();
    expect(item('Light')).toBeInTheDocument();
    expect(item('Dark')).toBeInTheDocument();
  });

  it('shows the scheme in effect on the button, not the stored preference', () => {
    stubMatchMedia(true); // OS says dark, nothing stored: "System" paints dark
    renderShell();
    expect(headerButton()).toHaveAttribute('data-scheme', 'dark');
    fireEvent.click(openHeaderMenu().item('Light'));
    expect(headerButton()).toHaveAttribute('data-scheme', 'light');
  });

  it('marks which option is current', () => {
    renderShell();
    const { item } = openHeaderMenu();
    // Uncontroversial default: no stored key, so "System" is current and the
    // other two are not.
    expect(item('System')).toHaveAttribute('aria-current', 'true');
    expect(item('Light')).not.toHaveAttribute('aria-current');
    expect(item('Dark')).not.toHaveAttribute('aria-current');
  });

  it('choosing Dark sets data-theme, writes localStorage, and closes the menu', () => {
    renderShell();
    fireEvent.click(openHeaderMenu().item('Dark'));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(openHeaderMenu().item('Dark')).toHaveAttribute('aria-current', 'true');
  });

  it('choosing Light sets data-theme and writes localStorage', () => {
    renderShell();
    fireEvent.click(openHeaderMenu().item('Light'));
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('choosing System removes the stored key and re-reads the OS query', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    stubMatchMedia(false); // OS says light
    renderShell();

    // Starts from the stored explicit choice.
    const { item } = openHeaderMenu();
    expect(item('Dark')).toHaveAttribute('aria-current', 'true');

    fireEvent.click(item('System'));

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe('light'); // the OS query, not the old choice
    expect(openHeaderMenu().item('System')).toHaveAttribute('aria-current', 'true');
  });

  it('keeps the footer copy in step with a choice made in the header, without a remount', () => {
    renderShell();
    fireEvent.click(openHeaderMenu().item('Dark'));
    // Both mount independently (see `theme.ts`'s `useThemePreference`); this is
    // the subscription that is supposed to stop them drifting apart.
    fireEvent.click(footerButton());
    const footerMenu = within(within(screen.getByRole('contentinfo')).getByRole('menu'));
    expect(footerMenu.getByRole('menuitem', { name: 'Dark' })).toHaveAttribute('aria-current', 'true');
    expect(footerMenu.getByRole('menuitem', { name: 'System' })).not.toHaveAttribute('aria-current');
  });
});
