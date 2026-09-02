import type { MetaFunction } from 'react-router';

import PricingPage from '../../src/pages/PricingPage';
import { loadPlans, type PlanCard } from '../../src/config/plans';
import { canonicalUrl } from '../../src/config/site';

/**
 * Read on the server, at request time.
 *
 * SSR is what makes this work: the prices are in the HTML a crawler sees, and the browser never
 * makes a cross-origin call for them — so no CORS entry, and no flash of a page without its prices.
 */
export async function loader() {
  return { plans: await loadPlans() };
}

export default function Pricing({ loaderData }: { loaderData: { plans: PlanCard[] } }) {
  return <PricingPage plans={loaderData.plans} />;
}

export const meta: MetaFunction = () => [
  { title: 'Pricing · Humbugg' },
  {
    name: 'description',
    content:
      'Humbugg is free for an exchange of up to six. Plus is a one-time upgrade for a bigger one; Work is an annual plan for companies.',
  },
  { name: 'robots', content: 'index, follow' },
  { tagName: 'link', rel: 'canonical', href: canonicalUrl('/pricing') },
];
