import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { LEGAL_LINKS } from '../config/policies';
import { APP_ORIGIN } from '../config/site';
import { Shell } from './Layout';

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
    expect(screen.getByRole('link', { name: 'Start a group' })).toHaveAttribute('href', `${APP_ORIGIN}/signup`);
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
