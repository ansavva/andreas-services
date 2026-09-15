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
  it('leads with the pitch and sends the CTA to the app sign-in', () => {
    renderAt('/');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('More wonder.');
    // The conversion path: this href silently regressing is the failure worth pinning.
    expect(screen.getByRole('link', { name: 'Create your exchange' })).toHaveAttribute(
      'href',
      `${APP_ORIGIN}/login`,
    );
  });

  it('sells the chat as a feature of its own, on Free', () => {
    renderAt('/');
    expect(screen.getByRole('heading', { level: 2, name: 'Ask them anything. Stay a secret.' })).toBeInTheDocument();
    // The recipient's side never sees a name: this is the wording the app uses, pinned so the site
    // cannot promise more anonymity — or less — than the product gives.
    expect(screen.getAllByText('Your Secret Santa').length).toBeGreaterThan(0);
    expect(screen.getByText('Included in Free.')).toBeInTheDocument();
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
