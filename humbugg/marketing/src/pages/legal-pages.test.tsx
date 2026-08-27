import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { POLICY_VERSION } from '../config/policies';
import BillingPage from './BillingPage';
import PrivacyPage from './PrivacyPage';
import RefundPage from './RefundPage';
import TermsPage from './TermsPage';

// One test per published policy: each must render under its own title and carry the
// current policy version — the version string is what the app's consent record cites,
// so a page silently falling behind it is a compliance bug, not a typo.
const PAGES = [
  { name: 'Privacy Policy', Page: PrivacyPage },
  { name: 'Terms of Service', Page: TermsPage },
  { name: 'Refund Policy', Page: RefundPage },
  { name: 'Billing Terms', Page: BillingPage },
] as const;

describe('legal pages', () => {
  for (const { name, Page } of PAGES) {
    it(`${name} renders titled and versioned`, () => {
      render(
        <MemoryRouter>
          <Page />
        </MemoryRouter>,
      );
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(name);
      expect(screen.getByText(new RegExp(`Version ${POLICY_VERSION.replace('.', '\\.')}`))).toBeInTheDocument();
    });
  }
});
