import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { LEGAL_LINKS } from '../config/policies';
import { APP_ORIGIN } from '../config/site';
import { Shell, SiteFooter } from './Layout';

function renderShell() {
  return render(
    <MemoryRouter>
      <Shell>
        <p>page body</p>
      </Shell>
    </MemoryRouter>,
  );
}

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
