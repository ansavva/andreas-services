import { Link } from 'react-router';

import { LegalPage } from '../components/LegalPage';
import { BUSINESS_NAME, SERVICE_COUNTRY, SUPPORT_EMAIL } from '../config/policies';

interface StoredItem {
  keys: string;
  store: string;
  purpose: string;
  lifetime: string;
}

// The complete inventory of what the product app stores on a device, verified against
// app/src/auth/oauth.ts, app/src/utils/session-store.ts, and app/src/utils/plus-intent.ts.
// The marketing site itself sets no cookies and uses no localStorage/sessionStorage.
const STORED_ITEMS: readonly StoredItem[] = [
  {
    keys: 'humbugg.auth.accessToken, humbugg.auth.refreshToken, humbugg.auth.idToken, humbugg.auth.expiresAt',
    store: 'localStorage on the web; the device secure store (expo-secure-store) in the native app',
    purpose: 'Keeps you signed in across tabs and restarts',
    lifetime: 'Until sign-out or token expiry',
  },
  {
    keys: 'humbugg:returnTo',
    store: 'sessionStorage',
    purpose: 'Where to send you after sign-in',
    lifetime: 'The browser tab',
  },
  {
    keys: 'humbugg:oauthVerifier, humbugg:oauthState',
    store: 'sessionStorage',
    purpose: 'Protects the sign-in handshake (PKCE, CSRF)',
    lifetime: 'The sign-in round trip',
  },
  {
    keys: 'humbugg:invite:{groupId}',
    store: 'sessionStorage',
    purpose: 'The invitation link you just created, so it can be shown again',
    lifetime: 'The tab',
  },
  {
    keys: 'humbugg:join:{groupId}',
    store: 'sessionStorage',
    purpose: 'Carries an invitation through sign-in',
    lifetime: 'The tab',
  },
  {
    keys: 'humbugg.plus.intent',
    store: 'AsyncStorage — persists across tab close',
    purpose: 'Remembers a Plus purchase you started, across the Stripe Checkout round trip',
    lifetime: 'Cleared when the purchase resolves',
  },
] as const;

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      summary={`This policy explains what information ${BUSINESS_NAME} collects, why we collect it, and the choices you have.`}
    >
      <h2>1. Scope</h2>
      <p>
        This policy covers personal information handled by {BUSINESS_NAME} (&ldquo;Humbugg&rdquo;) when you use our gift
        exchange service. Humbugg currently serves people in the {SERVICE_COUNTRY}. We aim to collect only what we need to
        run your exchange.
      </p>

      <h2>2. Account information</h2>
      <p>
        When you create an account we collect your email address and the password credentials handled by our
        authentication provider (AWS Cognito). We use this to sign you in, secure your account, and send account-related
        messages such as confirmation and password-reset codes.
      </p>

      <h2>3. Email and invitations</h2>
      <p>
        We send transactional email &mdash; for example confirmation codes, password resets, and exchange-related
        notices. To do this we process the recipient email address and keep a delivery record (such as whether a message
        was sent or bounced) so we can troubleshoot problems. We do not sell email addresses or use them for unrelated
        marketing.
      </p>

      <h2>4. Exchange and wish-list content</h2>
      <p>
        When you organize or join an exchange, we store the details you enter: your display name, the group name and
        notes, wish lists, avoid-lists, and pairing exclusions. This information is shared within the exchange as needed
        to run it &mdash; for example, a giver can see their assigned recipient&rsquo;s wish list.
      </p>

      <h2>5. Shipping addresses</h2>
      <p>
        Providing a shipping address is optional. If you add one, we store it so the person assigned to give you a gift
        can send it. An address you enter is visible to the participant matched with you and to the organizer of that
        exchange. Only share an address you are comfortable sharing for that purpose.
      </p>

      <h2>6. Draw and audit records</h2>
      <p>
        When an exchange is drawn we store the private giver-to-recipient assignments so each person can see their match.
        We also keep audit records of sensitive actions, such as an organizer using an emergency reveal, so there is an
        accurate history of what happened in an exchange.
      </p>

      <h2>7. Analytics and technical data</h2>
      <p>
        We keep server and application logs (such as request information and error details) to operate the service, keep
        it secure, and diagnose problems. We use this technical and usage information in aggregate to understand how
        Humbugg is used and to improve it. We do not use it to build advertising profiles about you.
      </p>

      <h2>8. Cookies and local storage</h2>
      <p>
        Humbugg uses only strictly necessary and functional storage &mdash; there are no third-party analytics,
        advertising, or tracking cookies. Our product analytics is recorded server-side, in aggregate, and cannot be
        tied back to your wish list, address, email, tokens, or assignment (see &ldquo;Analytics and technical
        data&rdquo; above). Because nothing here is used to track you across sites or to build an advertising profile,
        Humbugg does not show a cookie-consent banner.
      </p>
      <p>{BUSINESS_NAME}&rsquo;s marketing site (the pages this policy is published on) sets no cookies and stores
        nothing in your browser. The table below is what the Humbugg product app itself stores on your device:</p>
      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[42rem] border-collapse text-left text-sm">
          <caption className="sr-only">What the Humbugg product app stores on your device</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Key</th>
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Store</th>
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Purpose</th>
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Lifetime</th>
            </tr>
          </thead>
          <tbody>
            {STORED_ITEMS.map((item) => (
              <tr key={item.keys} className="border-b border-line align-top">
                <th scope="row" className="py-3 pr-4 font-mono text-xs font-medium text-ink">{item.keys}</th>
                <td className="py-3 pr-4 text-muted">{item.store}</td>
                <td className="py-3 pr-4 text-muted">{item.purpose}</td>
                <td className="py-3 pr-4 text-muted">{item.lifetime}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        If Humbugg ever adds a non-essential cookie or a client-side analytics tool, we will update this section and
        add a consent mechanism before doing so.
      </p>

      <h2>9. Payment information</h2>
      <p>
        Paid plans are handled by a third-party payment provider. Your card details are entered with that provider &mdash;
        Humbugg does not receive or store your full card number. We keep a record of your plan, purchase, and billing
        status so we can provide the service you paid for and handle refunds. See our{' '}
        <Link to="/billing">Billing Terms</Link> and <Link to="/refunds">Refund Policy</Link> for more.
      </p>

      <h2>10. How we share information</h2>
      <p>We share personal information only in these situations:</p>
      <ul>
        <li>Within an exchange, with its participants and organizer, as needed to run it.</li>
        <li>
          With service providers that operate Humbugg on our behalf &mdash; for hosting, databases, email delivery, and
          payment processing &mdash; under obligations to protect it. Our current sub-processors, what each one does,
          and how international transfers are protected are listed on the <Link to="/sub-processors">Sub-processors</Link> page.
        </li>
        <li>When the law requires it, or to protect the rights, safety, and security of people and the service.</li>
      </ul>
      <p>We do not sell your personal information.</p>

      <h2>11. Keeping and deleting information</h2>
      <p>
        We keep your information while your account is active and as needed to provide the service. You can delete your
        account, which removes your profile and the exchange content tied to it, subject to a short period needed to
        complete the deletion across our systems. We may retain limited records where we must for legal, security, or
        legitimate business reasons &mdash; for example, basic billing history and audit records. Backups are cleared on a
        rolling schedule.
      </p>

      <h2>12. Security</h2>
      <p>
        We use reasonable technical and organizational measures to protect your information, including encrypted
        connections and access controls. No online service can be completely secure, so we cannot guarantee absolute
        security, but we work to protect your information and to respond promptly to issues.
      </p>

      <h2>13. Your choices</h2>
      <p>
        You can review and update much of your information directly in Humbugg, and you can delete your account. If you
        would like help accessing or deleting your information, contact us at{' '}
        <a className="text-accent hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>
          {SUPPORT_EMAIL}
        </a>
        .
      </p>
      <h3>Requesting restriction or objection</h3>
      <p>
        Access, rectification, erasure, and export of your information are self-service &mdash; use the export and
        deletion tools in Settings, and the edit screens for your profile, wish list, and address. For a request to
        restrict how we process your data (Art. 18), an objection to processing (Art. 21), or a change that is not
        self-service &mdash; such as changing the email address on your account &mdash; email{' '}
        <a className="text-accent hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>
          {SUPPORT_EMAIL}
        </a>
        . We may ask you to confirm the request from your account&rsquo;s own email address before acting on it. We
        respond within one month; for a complex request we may extend that by up to two further months, and we will
        tell you if we do.
      </p>

      <h2>14. Children</h2>
      <p>
        Humbugg is not directed to children under 13, and we do not knowingly collect their personal information. If you
        believe a child has provided us information, contact us and we will remove it.
      </p>

      <h2>15. Changes to this policy</h2>
      <p>
        We may update this policy over time. When we do, we will change the version and effective date shown at the top of
        this page.
      </p>
    </LegalPage>
  );
}
