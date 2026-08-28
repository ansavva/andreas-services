import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { APP_ORIGIN } from '../config/site';
import LandingPage from './LandingPage';

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <LandingPage />
    </MemoryRouter>,
  );
}

describe('LandingPage', () => {
  it('leads with the pitch and sends the CTA to the app signup', () => {
    renderAt('/');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('More wonder.');
    // The conversion path: this href silently regressing is the failure worth pinning.
    expect(screen.getByRole('link', { name: 'Create your exchange' })).toHaveAttribute(
      'href',
      `${APP_ORIGIN}/signup`,
    );
  });

  it('acknowledges a deleted account only when the app says so', () => {
    renderAt('/?account_deleted=1');
    expect(screen.getByRole('status')).toHaveTextContent('Your account was deleted.');
  });

  it('shows no deletion banner on an ordinary visit', () => {
    renderAt('/');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
