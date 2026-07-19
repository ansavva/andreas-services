import { Link } from 'react-router';

import { LegalPage } from '../components/LegalPage';
import { BUSINESS_NAME, SERVICE_CURRENCY, SUPPORT_EMAIL } from '../config/policies';

export default function RefundPage() {
  return (
    <LegalPage
      title="Refund Policy"
      summary={`When ${BUSINESS_NAME} refunds a payment, and how to ask for one.`}
    >
      <h2>1. Full refund before the draw</h2>
      <p>
        If you upgrade an exchange (Plus) or subscribe to Work and change your mind, you can request a{' '}
        <strong>full refund of that charge before the exchange is drawn</strong>. As long as the exchange you paid for has
        not yet been drawn, we will refund the charge in full to your original payment method.
      </p>

      <h2>2. After the draw</h2>
      <p>
        Once an exchange has been drawn, the paid features have been delivered, so refunds after the draw are{' '}
        <strong>at our discretion</strong>. We look at these requests case by case and try to be fair &mdash; for example
        where something went wrong on our side &mdash; but a refund after the draw is not guaranteed.
      </p>

      <h2>3. Duplicate and failed charges are always covered</h2>
      <p>
        Regardless of timing, we will <strong>always refund a duplicate charge or a charge made in error</strong>. If you
        are billed more than once for the same purchase, or charged for something you did not buy, contact us and we will
        return the extra amount.
      </p>

      <h2>4. Work renewals</h2>
      <p>
        The Work plan renews automatically each year. You can cancel at any time to stop future renewals &mdash; see the{' '}
        <Link to="/billing">Billing Terms</Link>. If a renewal charge is made, the rules above apply: a full refund is
        available before you have used that renewal year&rsquo;s paid features to draw an exchange, and after that refunds
        are at our discretion. Duplicate or erroneous renewal charges are always refunded.
      </p>

      <h2>5. How refunds are issued</h2>
      <p>
        Refunds go back to your original payment method through our payment provider. Once we approve a refund it is
        usually processed within a few business days, though your bank may take longer to show it. All refunds are made in{' '}
        {SERVICE_CURRENCY}.
      </p>

      <h2>6. How to request a refund</h2>
      <p>
        Email us at{' '}
        <a className="text-accent hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>
          {SUPPORT_EMAIL}
        </a>{' '}
        with the account email and the exchange or charge involved, and we will help.
      </p>

      <h2>7. Changes to this policy</h2>
      <p>
        We may update this refund policy over time. When we do, we will change the version and effective date shown at the
        top of this page.
      </p>
    </LegalPage>
  );
}
