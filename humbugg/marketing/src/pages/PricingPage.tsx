import { buttonClass } from '@ansavva/design-system';
import { Link } from 'react-router';

import { Shell } from '../components/Layout';
import { appUrl, canonicalUrl } from '../config/site';
import type { PlanCard } from '../config/plans';

/**
 * What each plan is for, and what it actually does.
 *
 * The COPY lives here; every number — price, cadence, participant limit — arrives from the API and
 * is never written down in this file. That split is the point of #158: a figure typed into
 * marketing is a figure that drifts from what Stripe charges, and nobody notices until somebody is
 * charged something the page did not say.
 */
const COPY: Record<string, { who: string; lead: string; features: string[] }> = {
  free: {
    who: 'For one exchange with friends or family',
    lead: 'Everything you need to run a draw — wish lists, exclusions and private assignments.',
    features: [
      'Share a private link and people join themselves',
      'Wish lists, with links and prices',
      'Exclusions, so couples are not matched',
      'A private draw nobody can see into',
      'Ask your recipient a question anonymously',
    ],
  },
  plus: {
    who: 'For a bigger exchange, or one you would rather not chase',
    lead: 'Everything in Free, and Humbugg does the organizing you would otherwise do by hand.',
    features: [
      'Send invitations by email and see who has not answered',
      'Automatic reminders, so you are not the one chasing',
      'Co-organizers who can run it alongside you',
      'Your own greeting, instructions and colours',
      'Save the setup as a template for next year',
      'Add somebody after the draw, changing as few matches as possible',
    ],
  },
  work: {
    who: 'For a company running exchanges across teams',
    lead: 'An organization workspace, with every exchange and every organizer in one place.',
    features: [
      'One workspace holding many exchanges at once',
      'A people directory shared across them',
      'Administration and roles for whoever runs it',
      'Your branding on what employees see',
      'Central billing, on one invoice',
    ],
  },
};

export default function PricingPage({ plans }: { plans: PlanCard[] }) {
  return (
    <Shell>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'Product',
            name: 'Humbugg',
            description: 'A private, self-service Secret Santa organizer.',
            url: canonicalUrl('/pricing'),
            offers: plans.map((plan) => ({
              '@type': 'Offer',
              name: plan.name,
              price: (plan.priceCents / 100).toFixed(2),
              priceCurrency: plan.currency,
              url: canonicalUrl('/pricing'),
            })),
          }),
        }}
      />

      <section className="border-b border-line">
        <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <p className="eyebrow">Pricing</p>
          <h1 className="mt-5 max-w-3xl font-heading text-5xl font-semibold leading-[1.05] tracking-[-.03em] text-ink">
            Start free. Pay only when an exchange outgrows it.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-muted">
            No subscription for an exchange between friends, and no card to start. Prices are in{' '}
            {plans[0]?.currency ?? 'USD'}.
          </p>

          <div className="mt-14 grid gap-6 lg:grid-cols-3">
            {plans.map((plan) => (
              <PlanColumn key={plan.code} plan={plan} />
            ))}
          </div>

          <p className="mt-10 max-w-3xl text-sm text-muted">
            Every participant limit counts everybody in the exchange, the organizer included. Full
            terms are in the <Link className="link" to="/billing">Billing Terms</Link>, and what we
            refund is in the <Link className="link" to="/refunds">Refund Policy</Link>.
          </p>
        </div>
      </section>

      <ComparisonTable plans={plans} />
    </Shell>
  );
}

function PlanColumn({ plan }: { plan: PlanCard }) {
  const copy = COPY[plan.code];
  const featured = plan.code === 'plus';
  return (
    <div
      className={`flex flex-col rounded-2xl border bg-card p-8 ${
        featured ? 'border-primary shadow-lg' : 'border-line'
      }`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-heading text-2xl font-semibold text-ink">{plan.name}</h2>
        {featured ? (
          <span className="rounded-full bg-surface-alt px-3 py-1 text-xs font-semibold text-primary">
            Most chosen
          </span>
        ) : null}
      </div>

      <p className="mt-2 text-sm text-muted">{copy?.who}</p>

      <p className="mt-6 font-heading text-4xl font-semibold tracking-[-.03em] text-ink">
        {plan.price}
      </p>
      {/*
        The cadence is the thing an unhappy customer will say they were not told. One-time and
        automatically renewing are set in the same weight as the price rather than a footnote, and
        `cadence` is derived from the API's `billing_cadence` rather than written per plan.
      */}
      <p className="mt-1 text-sm font-semibold text-ink">{plan.cadence}</p>
      <p className="mt-1 text-sm text-muted">{plan.limitLabel}</p>

      <p className="mt-6 text-sm leading-6 text-muted">{copy?.lead}</p>

      <ul className="mt-6 flex-1 space-y-3 text-sm text-ink">
        {copy?.features.map((feature) => (
          <li key={feature} className="flex gap-3">
            <span aria-hidden="true" className="mt-[.35rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
            <span>{feature}</span>
          </li>
        ))}
      </ul>

      <div className="mt-8">
        <a
          className={buttonClass({ intent: featured ? 'primary' : 'secondary' })}
          href={appUrl(plan.code === 'free' ? '/signup' : '/')}
        >
          {plan.code === 'free'
            ? 'Start free'
            : plan.code === 'plus'
              ? 'Upgrade an exchange'
              : 'Start Work'}
        </a>
      </div>
    </div>
  );
}

/**
 * The one thing the three columns cannot show: the same question answered for each plan.
 *
 * "Who sends the invitations" is the difference people actually feel between Free and Plus, so it
 * is the first row rather than a bullet two thirds down a list.
 */
function ComparisonTable({ plans }: { plans: PlanCard[] }) {
  const rows: Array<{ label: string; values: Record<string, string> }> = [
    {
      label: 'Getting people in',
      values: {
        free: 'You share a private link',
        plus: 'Humbugg emails them, and tracks who has not answered',
        work: 'Humbugg emails them, from your directory',
      },
    },
    {
      label: 'Chasing people',
      values: { free: 'You do', plus: 'Automatic reminders', work: 'Automatic reminders' },
    },
    {
      label: 'People per exchange',
      values: Object.fromEntries(
        plans.map((plan) => [
          plan.code,
          plan.marketedAsUnlimited ? 'No limit' : plan.participantLimit.toLocaleString('en-US'),
        ]),
      ),
    },
    {
      label: 'Exchanges',
      values: { free: 'One at a time', plus: 'Upgrade each one you need', work: 'As many as you run' },
    },
    {
      label: 'Who can organize',
      values: { free: 'You', plus: 'You and co-organizers', work: 'Administrators and organizers' },
    },
    {
      label: 'Branding',
      values: { free: 'Humbugg’s', plus: 'Your greeting and colours', work: 'Your organization’s' },
    },
    {
      label: 'Billing',
      values: Object.fromEntries(plans.map((plan) => [plan.code, plan.cadence])),
    },
  ];

  return (
    <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
      <h2 className="font-heading text-3xl font-semibold tracking-[-.02em] text-ink">
        Side by side
      </h2>
      {/* Wide content scrolls inside its own container rather than the page. */}
      <div className="mt-8 overflow-x-auto">
        <table className="w-full min-w-[42rem] border-collapse text-left text-sm">
          <caption className="sr-only">Humbugg plans compared</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="py-4 pr-4 font-semibold text-ink">What you get</th>
              {plans.map((plan) => (
                <th key={plan.code} scope="col" className="py-4 pr-4 font-semibold text-ink">
                  {plan.name}
                  <span className="block text-xs font-normal text-muted">
                    {plan.price} · {plan.cadence}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-b border-line align-top">
                <th scope="row" className="py-4 pr-4 font-medium text-muted">{row.label}</th>
                {plans.map((plan) => (
                  <td key={plan.code} className="py-4 pr-4 text-ink">{row.values[plan.code] ?? '—'}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
