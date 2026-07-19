import { Link } from 'react-router';

import { LegalPage } from '../components/LegalPage';
import { BUSINESS_NAME, SERVICE_COUNTRY, SERVICE_CURRENCY } from '../config/policies';

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      summary={`These terms explain what you can expect from ${BUSINESS_NAME} and what we ask of you when organizing or joining a gift exchange.`}
    >
      <h2>1. Who these terms cover</h2>
      <p>
        {BUSINESS_NAME} (&ldquo;Humbugg,&rdquo; &ldquo;we,&rdquo; or &ldquo;us&rdquo;) provides a self-service tool for
        organizing Secret Santa&ndash;style gift exchanges. By creating an account, organizing an exchange, or joining one
        through an invitation, you agree to these terms. If you do not agree, please do not use Humbugg.
      </p>
      <p>
        Humbugg is offered to people in the {SERVICE_COUNTRY} and is priced in {SERVICE_CURRENCY}. It is intended for
        personal and workplace gift exchanges, not for regulated, high-value, or commercial transactions.
      </p>

      <h2>2. Your account</h2>
      <p>
        You need an account to organize or participate in an exchange. Keep your sign-in details private and let us know if
        you believe someone else has accessed your account. You are responsible for activity that happens under your
        account. You must be old enough to form a binding agreement in your jurisdiction to use Humbugg.
      </p>

      <h2>3. Organizer responsibilities</h2>
      <p>If you create and run an exchange, you are the organizer. As organizer you agree to:</p>
      <ul>
        <li>Only invite people who want to take part, and give them accurate details about the exchange.</li>
        <li>
          Collect and share participant information &mdash; such as names, wish lists, avoid-lists, and optional shipping
          addresses &mdash; only for the purpose of running that exchange.
        </li>
        <li>Set a spending limit and dates that reflect what participants have actually agreed to.</li>
        <li>Handle the wish lists and addresses that participants share with reasonable care.</li>
        <li>
          Draw the exchange, and reveal assignments, honestly &mdash; Humbugg keeps each assignment private, and you agree
          not to try to expose who was matched with whom.
        </li>
      </ul>
      <p>
        You are responsible for the conduct of the exchange you organize. Humbugg provides the coordination tool; it does
        not purchase, ship, or guarantee any gifts.
      </p>

      <h2>4. Invitations</h2>
      <p>
        Invitation links let people join a specific exchange. Only share an invitation link with people you intend to
        include. Do not post invitation links publicly, sell them, or use them to add people who have not agreed to
        participate. We may disable an invitation link that appears to be misused.
      </p>

      <h2>5. Acceptable use</h2>
      <p>When using Humbugg, you agree not to:</p>
      <ul>
        <li>Use the service for anything unlawful, deceptive, harassing, or harmful.</li>
        <li>Upload content you do not have the right to share, or that is abusive, hateful, or obscene.</li>
        <li>
          Enter someone else&rsquo;s personal information without a legitimate reason connected to the exchange and their
          agreement to take part.
        </li>
        <li>Attempt to break, overload, reverse engineer, or gain unauthorized access to the service or its data.</li>
        <li>Use Humbugg to send spam or to collect addresses for purposes unrelated to the exchange.</li>
      </ul>
      <p>We may suspend or close accounts that violate these terms or that put other people or the service at risk.</p>

      <h2>6. Plans and limits</h2>
      <p>
        Humbugg offers a Free plan and paid Plus and Work plans. Each plan sets how many people can take part in an
        exchange and how the exchange is billed. The current plans, prices, participant limits, and renewal terms are
        described in our <Link to="/billing">Billing Terms</Link>. Paid plans are billed in {SERVICE_CURRENCY}. We may
        change plan features or prices going forward, and we will apply any changes to future charges only, not
        retroactively.
      </p>

      <h2>7. Assignments and the draw</h2>
      <p>
        Humbugg matches participants using their exclusions (pairings you tell it to avoid) and each person&rsquo;s
        participation status. A few things to understand about the draw:
      </p>
      <ul>
        <li>
          Some combinations of exclusions make a valid draw impossible. When that happens the draw cannot complete until
          the exclusions or participants change.
        </li>
        <li>Once an exchange is drawn, the assignments are fixed for that exchange unless the organizer resets it.</li>
        <li>
          Assignments are shown privately to each participant. We take reasonable steps to keep them private but cannot
          guarantee that a participant will not reveal their own assignment.
        </li>
        <li>
          Humbugg does not verify that gifts are actually bought, sent, or received. That part is up to the participants.
        </li>
      </ul>

      <h2>8. Your content</h2>
      <p>
        You keep ownership of the information you enter, such as group details and wish lists. You give us permission to
        store and process that information so we can operate the exchange for you. How we handle personal information is
        described in our <Link to="/privacy">Privacy Policy</Link>.
      </p>

      <h2>9. Service availability</h2>
      <p>
        We work to keep Humbugg available and running well, but we provide the service &ldquo;as is&rdquo; and cannot
        promise it will be uninterrupted or error-free. We may update, change, or discontinue features. To the extent the
        law allows, Humbugg is not liable for indirect or incidental losses, and our total responsibility to you for the
        service is limited to the amount you paid us for it in the twelve months before the issue arose.
      </p>

      <h2>10. Ending your use</h2>
      <p>
        You can stop using Humbugg and delete your account at any time. We may suspend or end access if these terms are
        broken. How refunds work if you have paid for a plan is explained in our <Link to="/refunds">Refund Policy</Link>.
      </p>

      <h2>11. Changes to these terms</h2>
      <p>
        We may update these terms as Humbugg grows. When we do, we will change the version and effective date shown at the
        top of this page. If you keep using Humbugg after an update, that means you accept the updated terms.
      </p>
    </LegalPage>
  );
}
