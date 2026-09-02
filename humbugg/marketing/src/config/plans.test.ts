import { afterEach, describe, expect, it, vi } from 'vitest';

import { FALLBACK, LEGAL_PLAN_FACTS, loadPlans, toCards } from './plans';

const CATALOGUE = [
  { code: 'free', name: 'Free', participant_limit: 6, marketed_as_unlimited: false, price_cents: 0, currency: 'USD', billing_cadence: 'free' as const },
  { code: 'plus', name: 'Plus', participant_limit: 50, marketed_as_unlimited: false, price_cents: 1_200, currency: 'USD', billing_cadence: 'one_time' as const },
  { code: 'work', name: 'Work', participant_limit: 10_000, marketed_as_unlimited: true, price_cents: 9_900, currency: 'USD', billing_cadence: 'annual' as const },
];

afterEach(() => vi.unstubAllGlobals());

function respondWith(body: unknown, ok = true, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  }));
}

describe('toCards', () => {
  it('orders the plans the way they are sold, whatever order they arrive in', () => {
    const cards = toCards([CATALOGUE[2], CATALOGUE[0], CATALOGUE[1]]);
    expect(cards.map((card) => card.code)).toEqual(['free', 'plus', 'work']);
  });

  it('drops the cents on a whole amount, because $12.00 reads like a subscription row', () => {
    expect(toCards([CATALOGUE[1]])[0].price).toBe('$12');
    expect(toCards([{ ...CATALOGUE[1], price_cents: 1_250 }])[0].price).toBe('$12.50');
  });

  it('says "no limit" where the number is a safety ceiling rather than a boundary', () => {
    const work = toCards([CATALOGUE[2]])[0];
    expect(work.limitLabel).toBe('No participant limit');
    expect(work.limitLabel).not.toContain('10,000');
  });

  it('ignores a plan code the pages have no copy for', () => {
    const cards = toCards([...CATALOGUE, { ...CATALOGUE[0], code: 'enterprise' }]);
    expect(cards.map((card) => card.code)).toEqual(['free', 'plus', 'work']);
  });
});

describe('loadPlans', () => {
  it('reads the catalogue when the API answers', async () => {
    respondWith(CATALOGUE);
    const cards = await loadPlans();
    expect(cards.map((card) => card.price)).toEqual(['$0', '$12', '$99']);
  });

  // A pricing page that 500s because the API blinked is worse than one a deploy out of date.
  it('falls back rather than failing, when the API does not answer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')));
    await expect(loadPlans()).resolves.toEqual(FALLBACK);
  });

  it('falls back on a non-200, rather than rendering an error body as plans', async () => {
    respondWith({ error: 'nope' }, false, 503);
    await expect(loadPlans()).resolves.toEqual(FALLBACK);
  });

  // An empty array is a 200, so nothing else would have caught it — and it would render a pricing
  // page with no prices on it.
  it('falls back when the catalogue comes back empty', async () => {
    respondWith([]);
    await expect(loadPlans()).resolves.toEqual(FALLBACK);
  });
});

/**
 * The fallback is a second copy of the figures, and this is what stops it drifting.
 *
 * `policies.ts` states the same prices in the Billing Terms and the Refund Policy, which are legal
 * copy — so if the fallback and the legal pages ever disagreed, one of the two would be telling a
 * customer something untrue about what they were charged.
 */
describe('the fallback and the legal copy', () => {
  it('state the same price for every plan', () => {
    for (const fact of LEGAL_PLAN_FACTS) {
      const card = FALLBACK.find((candidate) => candidate.code === fact.code);
      expect(card, `no fallback card for ${fact.code}`).toBeDefined();
      expect(card!.price).toBe(fact.price);
    }
  });

  it('cover exactly the same set of plans', () => {
    expect(FALLBACK.map((card) => card.code).sort()).toEqual(
      LEGAL_PLAN_FACTS.map((fact) => fact.code).slice().sort(),
    );
  });
});
