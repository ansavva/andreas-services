import { Link } from 'react-router';

import { LegalPage } from '../components/LegalPage';
import {
  BUSINESS_NAME,
  PLANS,
  SERVICE_COUNTRY,
  SERVICE_CURRENCY,
} from '../config/policies';

export default function BillingPage() {
  return (
    <LegalPage
      title="Billing Terms"
      summary={`How Humbugg's plans are priced and charged. All prices are in ${SERVICE_CURRENCY} for customers in the ${SERVICE_COUNTRY}.`}
    >
      <h2>1. Plans</h2>
      <p>{BUSINESS_NAME} offers one free plan and two paid plans:</p>
      <ul>
        {PLANS.map((plan) => (
          <li key={plan.code}>
            <strong>
              {plan.name} &mdash; {plan.price} ({plan.cadence}).
            </strong>{' '}
            {plan.summary}
          </li>
        ))}
      </ul>
      <p>
        All amounts are shown and charged in {SERVICE_CURRENCY}. Applicable taxes, if any, may be added at checkout.
      </p>

      <h2>2. Plus is a one-time charge</h2>
      <p>
        Plus is a one-time upgrade for a single exchange. You pay once for that exchange to raise its participant limit;
        there is no recurring charge and nothing to cancel. If you want to run another exchange with a higher limit, you
        upgrade that exchange separately.
      </p>

      <h2>3. Work renews automatically each year</h2>
      <p>
        Work is an annual subscription. It costs $99 per year and <strong>renews automatically</strong> at the start of
        each new year unless you cancel. By subscribing to Work, you authorize us, through our payment provider, to charge
        your payment method $99 for the first year and again at each yearly renewal, at the then-current price, until you
        cancel.
      </p>
      <p>
        We will use reasonable efforts to remind you before a renewal charge. If the price changes, we will tell you
        before it applies to a renewal.
      </p>

      <h2>4. Canceling Work</h2>
      <p>
        You can cancel the Work plan at any time from your account or by contacting support. When you cancel, your plan
        stays active until the end of the current paid year and then does not renew &mdash; you will not be charged again.
        Canceling stops future renewals; whether a charge already made is refundable is covered by our{' '}
        <Link to="/refunds">Refund Policy</Link>.
      </p>

      <h2>5. Payment processing</h2>
      <p>
        Payments are processed by a third-party payment provider. You enter your card details with that provider, and
        Humbugg does not receive or store your full card number. You agree to provide accurate billing information and to
        keep your payment method current.
      </p>

      <h2>6. Failed or duplicate charges</h2>
      <p>
        If a charge fails, we may retry it or pause the paid features until payment succeeds. If you are ever charged more
        than once for the same purchase, or a charge is made in error, we will refund the extra or failed charge &mdash;
        see the <Link to="/refunds">Refund Policy</Link>.
      </p>

      <h2>7. Price changes</h2>
      <p>
        We may change plan prices or features in the future. Any change applies to new purchases and to Work renewals
        after we give notice; it does not change a one-time Plus charge you have already paid.
      </p>

      <h2>8. Changes to these terms</h2>
      <p>
        We may update these billing terms over time. When we do, we will change the version and effective date shown at
        the top of this page.
      </p>
    </LegalPage>
  );
}
