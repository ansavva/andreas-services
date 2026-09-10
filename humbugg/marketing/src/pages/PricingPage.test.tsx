import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { FALLBACK, toCards } from '../config/plans';
import { APP_ORIGIN } from '../config/site';
import PricingPage from './PricingPage';

function renderWith(plans = FALLBACK) {
  return render(
    <MemoryRouter>
      <PricingPage plans={plans} />
    </MemoryRouter>,
  );
}

describe('PricingPage', () => {
  it('shows the two plans with the figures it was given', () => {
    renderWith();
    for (const name of ['Free', 'Plus']) {
      expect(screen.getAllByRole('heading', { name, level: 2 }).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByText('$0').length).toBeGreaterThan(0);
    expect(screen.getAllByText('$12').length).toBeGreaterThan(0);
    expect(screen.queryByRole('heading', { name: 'Work', level: 2 })).not.toBeInTheDocument();
    expect(screen.queryByText('$99')).not.toBeInTheDocument();
  });

  /**
   * The half of a price people say they were not told.
   *
   * One-time and automatically renewing have to be distinguishable without reading both twice, so
   * this asserts the words rather than that some cadence text exists.
   */
  it('makes one-time unmistakable', () => {
    renderWith();
    expect(screen.getAllByText('Once, per exchange').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Always free').length).toBeGreaterThan(0);
  });

  /**
   * #158: do not market the internal 10,000 safety ceiling as a feature.
   *
   * It is a guard rail against a runaway import, not a product boundary. Work is hidden entirely
   * now, so this is the one number that must NOT appear.
   */
  it('never puts the 10,000 safety ceiling on the page', () => {
    const { container } = renderWith();
    expect(container.textContent).not.toContain('10,000');
    expect(container.textContent).not.toContain('10000');
  });

  it('states the limits that ARE product boundaries, organizer included', () => {
    renderWith();
    expect(
      screen.getByText('Up to 6 participants, organizer included'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Up to 50 participants, organizer included'),
    ).toBeInTheDocument();
  });

  it('says who sends the invitations, which is the difference people feel', () => {
    renderWith();
    const row = screen.getByRole('row', { name: /Getting people in/ });
    expect(within(row).getByText('You share a private link')).toBeInTheDocument();
    expect(
      within(row).getByText('Humbugg emails them, and tracks who has not answered'),
    ).toBeInTheDocument();
  });

  it('offers a start and an upgrade, no Work path', () => {
    renderWith();
    expect(screen.getByRole('link', { name: 'Start free' })).toHaveAttribute(
      'href',
      `${APP_ORIGIN}/login`,
    );
    expect(screen.getByRole('link', { name: 'Upgrade an exchange' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Start Work' })).not.toBeInTheDocument();
  });

  /**
   * Work is deferred (#638). Even if the API answers with a Work entry — a stored group that
   * predates the flag, or a rollback — the page must never show it.
   */
  it('never renders Work even if the API returns it', () => {
    const withWork = toCards([
      { code: 'free', name: 'Free', participant_limit: 6, marketed_as_unlimited: false, price_cents: 0, currency: 'USD', billing_cadence: 'free' },
      { code: 'plus', name: 'Plus', participant_limit: 50, marketed_as_unlimited: false, price_cents: 1_200, currency: 'USD', billing_cadence: 'one_time' },
      { code: 'work', name: 'Work', participant_limit: 10_000, marketed_as_unlimited: true, price_cents: 9_900, currency: 'USD', billing_cadence: 'annual' },
    ]);
    const { container } = renderWith(withWork);

    expect(container.textContent).not.toContain('Work');
    expect(container.textContent).not.toContain('$99');
    expect(screen.queryByRole('link', { name: 'Start Work' })).not.toBeInTheDocument();
    expect(container.textContent).not.toContain('renews automatically');
  });

  /**
   * Nothing on this page is written down twice.
   *
   * Every figure comes from the API payload, so a page rendered from different numbers shows those
   * numbers — which is the whole reason `/api/plans` was opened to the public. A price hard-coded
   * into the copy would survive this only by coincidence.
   */
  it('renders whatever the catalogue says, not what the copy remembers', () => {
    const changed = toCards([
      { code: 'free', name: 'Free', participant_limit: 8, marketed_as_unlimited: false, price_cents: 0, currency: 'USD', billing_cadence: 'free' },
      { code: 'plus', name: 'Plus', participant_limit: 60, marketed_as_unlimited: false, price_cents: 1_500, currency: 'USD', billing_cadence: 'one_time' },
    ]);
    const { container } = renderWith(changed);

    expect(screen.getAllByText('$15').length).toBeGreaterThan(0);
    expect(screen.getByText('Up to 60 participants, organizer included')).toBeInTheDocument();
    expect(container.textContent).not.toContain('$12');
  });
});
