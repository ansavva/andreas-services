import { Link } from 'react-router';

import { LegalPage } from '../components/LegalPage';
import { BUSINESS_NAME, SUPPORT_EMAIL } from '../config/policies';

interface SubProcessor {
  name: string;
  purpose: string;
  data: string;
  region: string;
  mechanism: string;
}

const SUB_PROCESSORS: readonly SubProcessor[] = [
  {
    name: 'Amazon Web Services, Inc. (AWS)',
    purpose: 'Hosting, authentication (Cognito), database (DynamoDB), file storage (S3), transactional email (SES)',
    data: 'Account identifiers, verified email address, exchange content, wish lists, addresses, audit records',
    region: 'us-east-1 (N. Virginia)',
    mechanism:
      'AWS GDPR Data Processing Addendum (incorporated in the AWS Service Terms) with EU Standard Contractual Clauses; UK Addendum',
  },
  {
    name: 'Stripe, Inc.',
    purpose: 'Payment processing for Plus',
    data: 'Name, email, and billing details as entered on Stripe Checkout — Humbugg never stores your card data',
    region: 'United States',
    mechanism: 'Stripe Data Processing Agreement (incorporated in the Stripe Services Agreement), SCCs',
  },
  {
    name: 'Google LLC (Google Workspace)',
    purpose: `The support mailbox, ${SUPPORT_EMAIL}`,
    data: 'Whatever you send to support',
    region: 'United States',
    mechanism: 'Google Workspace Data Processing Addendum, SCCs',
  },
] as const;

export default function SubProcessorsPage() {
  return (
    <LegalPage
      title="Sub-processors"
      summary={`The service providers ${BUSINESS_NAME} uses to process personal data on our behalf, and how each transfer out of the EEA/UK is protected.`}
    >
      <h2>Who processes data for us</h2>
      <p>
        We use a small number of service providers (&ldquo;sub-processors&rdquo;) to run Humbugg. Each one is bound by a
        data processing agreement that incorporates the EU Standard Contractual Clauses (SCCs), which is how personal
        data from the EEA/UK is protected when it reaches a provider in the United States. See our{' '}
        <Link to="/privacy">Privacy Policy</Link>, particularly &ldquo;How we share information.&rdquo;
      </p>

      <div className="mt-8 overflow-x-auto">
        <table className="w-full min-w-[48rem] border-collapse text-left text-sm">
          <caption className="sr-only">Humbugg sub-processors</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Processor</th>
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Purpose</th>
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Data categories</th>
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Region</th>
              <th scope="col" className="py-3 pr-4 font-semibold text-ink">Transfer mechanism</th>
            </tr>
          </thead>
          <tbody>
            {SUB_PROCESSORS.map((proc) => (
              <tr key={proc.name} className="border-b border-line align-top">
                <th scope="row" className="py-3 pr-4 font-medium text-ink">{proc.name}</th>
                <td className="py-3 pr-4 text-muted">{proc.purpose}</td>
                <td className="py-3 pr-4 text-muted">{proc.data}</td>
                <td className="py-3 pr-4 text-muted">{proc.region}</td>
                <td className="py-3 pr-4 text-muted">{proc.mechanism}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Changes to this list</h2>
      <p>
        We update this page before a new sub-processor starts handling personal data on our behalf. If you would like
        to be notified of changes, email us at{' '}
        <a className="text-accent hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>
          {SUPPORT_EMAIL}
        </a>
        .
      </p>
    </LegalPage>
  );
}
