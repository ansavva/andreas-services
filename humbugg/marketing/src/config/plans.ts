// The plan catalogue, as the pricing pages need it (#158).
//
// Every displayed figure comes from `GET /api/plans`, which is the same catalogue the backend
// checks capabilities against and the same one that carries Stripe's price ids. A number typed into
// marketing copy is a number that drifts from what a customer is actually charged, and nobody finds
// out until somebody pays something the page did not say.
import { apiUrl } from './site';
import { PLANS } from './policies';

/** What the API returns. Snake case, because that is what is on the wire. */
interface PlanDefinition {
  code: string;
  name: string;
  participant_limit: number;
  marketed_as_unlimited: boolean;
  price_cents: number;
  currency: string;
  billing_cadence: 'free' | 'one_time' | 'annual';
}

export interface PlanCard {
  code: string;
  name: string;
  /** Formatted for display — "$0", "$12", "$99". */
  price: string;
  priceCents: number;
  currency: string;
  /** How it is charged, in words. The half of a price people say they were not told. */
  cadence: string;
  participantLimit: number;
  /**
   * Whether the limit is a safety ceiling rather than a product boundary.
   *
   * Work's 10,000 is an internal guard against a runaway import, not a feature — #158 says in so
   * many words not to market it. The API already distinguishes the two, so the page reads the flag
   * instead of hard-coding which plan is which.
   */
  marketedAsUnlimited: boolean;
  /** The limit as it should be SAID: a number, or "No limit" where the number is a guard rail. */
  limitLabel: string;
}

const ORDER = ['free', 'plus', 'work'];

/**
 * How each cadence reads.
 *
 * `annual` says "automatically renewing" rather than "per year" alone, because the renewal is the
 * part that surprises people and #158 asks for it to be unmistakable. `one_time` says the opposite
 * just as plainly, so the contrast is visible without reading both twice.
 */
const CADENCE: Record<PlanDefinition['billing_cadence'], string> = {
  free: 'Always free',
  one_time: 'Once, per exchange',
  annual: 'Per year, renews automatically',
};

function money(cents: number, currency: string): string {
  const amount = cents / 100;
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

export function toCards(definitions: PlanDefinition[]): PlanCard[] {
  return definitions
    .filter((plan) => ORDER.includes(plan.code))
    .sort((a, b) => ORDER.indexOf(a.code) - ORDER.indexOf(b.code))
    .map((plan) => ({
      code: plan.code,
      name: plan.name,
      price: money(plan.price_cents, plan.currency),
      priceCents: plan.price_cents,
      currency: plan.currency,
      cadence: CADENCE[plan.billing_cadence] ?? '',
      participantLimit: plan.participant_limit,
      marketedAsUnlimited: plan.marketed_as_unlimited,
      limitLabel: plan.marketed_as_unlimited
        ? 'No participant limit'
        : `Up to ${plan.participant_limit.toLocaleString('en-US')} participants, organizer included`,
    }));
}

/**
 * The catalogue, read at request time on the server.
 *
 * A failure falls back to `policies.ts`, which the Billing Terms and Refund Policy already state
 * and which are reviewed as legal copy. That is a deliberate second copy, and it earns its place:
 * a pricing page that 500s because the API blinked is worse than one showing figures that are
 * correct but a deploy old. `plans.test.ts` asserts the two agree, so the fallback cannot go stale
 * silently.
 */
export async function loadPlans(): Promise<PlanCard[]> {
  try {
    const response = await fetch(apiUrl('/api/plans'), {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) throw new Error(`plans responded ${response.status}`);
    const cards = toCards((await response.json()) as PlanDefinition[]);
    if (cards.length === 0) throw new Error('plans returned nothing usable');
    return cards;
  } catch {
    return FALLBACK;
  }
}

/** The same figures the legal pages state, shaped as cards. Never shown unless the API is down. */
export const FALLBACK: PlanCard[] = toCards([
  { code: 'free', name: 'Free', participant_limit: 6, marketed_as_unlimited: false, price_cents: 0, currency: 'USD', billing_cadence: 'free' },
  { code: 'plus', name: 'Plus', participant_limit: 50, marketed_as_unlimited: false, price_cents: 1_200, currency: 'USD', billing_cadence: 'one_time' },
  // `marketed_as_unlimited` here for the same reason the catalogue sets it: the 10,000 is a guard
  // rail, and the fallback must not say something the live page would not.
  { code: 'work', name: 'Work', participant_limit: 10_000, marketed_as_unlimited: true, price_cents: 9_900, currency: 'USD', billing_cadence: 'annual' },
]);

/** Re-exported so the drift test can compare the fallback against the legal copy in one import. */
export { PLANS as LEGAL_PLAN_FACTS };
