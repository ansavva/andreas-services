import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Buying Plus (#141), through the export the way production builds it.
//
// The stubbed mode is where these belong: a real Checkout would take a card, and the assertions
// that matter are about what Humbugg says — the price it read from the server, the promise it does
// not make about renewal, and the four ways a return can land.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface Group {
  group_id: string;
}

test('the organizer sees the price the server sent, not one the app invented', async ({ page }) => {
  stubOnly('the live dev stack has its own plan configuration and may not have Stripe enabled');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  await page.goto(`/organize/${group.group_id}`);

  // $12 is `price_cents: 1200` in e2e/fixtures/plans.json. Change the fixture and this must move.
  await expect(page.getByText('$12 once, for this exchange')).toBeVisible();
  await expect(page.getByText('Upgrade this exchange — $12')).toBeVisible();
  await expect(page.getByText(/Up to 50 participants, instead of 6\./)).toBeVisible();
});

test('the offer never implies a renewal or a purchase that covers every exchange', async ({ page }) => {
  stubOnly('the copy under test is the stubbed export’s, and pinning it live adds nothing');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  await page.goto(`/organize/${group.group_id}`);

  await expect(page.getByText(/does not renew/)).toBeVisible();
  await expect(page.getByText(/next exchange starts on Free/)).toBeVisible();
});

test('a canceled return says nothing was charged and leaves the exchange on Free', async ({ page }) => {
  stubOnly('a live Checkout would need a card');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  // Exactly the URL Stripe's cancel_url returns to.
  await page.goto(`/organize/${group.group_id}?checkout=canceled`);

  await expect(page.getByText(/nothing was charged/)).toBeVisible();
  await expect(page.getByText('This exchange is on Free')).toBeVisible();
});

test('a paid return waits for the entitlement before it claims Plus', async ({ page }) => {
  stubOnly('a live Checkout would need a card');
  const group = fixture<Group>('group');
  await stubApi(page);
  await signIn(page);

  // The webhook is mid-flight: Stripe has taken the payment, Humbugg has not applied it. Overrides
  // the base stub, which Playwright consults last-registered-first.
  let polls = 0;
  await page.route(`**/api/groups/${group.group_id}/billing/plus`, (route) => {
    polls += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        group_id: group.group_id,
        status: 'paid',
        // The entitlement appears on the third read, as it would once the webhook lands.
        entitlement_id: polls >= 3 ? `plus:${group.group_id}` : null,
        receipt_url: 'https://receipt.stripe.test/r1',
      }),
    });
  });

  await page.goto(`/organize/${group.group_id}?checkout=success`);

  await expect(page.getByText('Confirming your payment with Stripe…')).toBeVisible();
  await expect(page.getByText('Plus is on for this exchange', { exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await expect(
    page.getByText('Payment confirmed. That is the only charge for this exchange — nothing renews.'),
  ).toBeVisible();
  await expect(page.getByText('View your Stripe receipt')).toBeVisible();
  // The entitlement, not the third poll's mere existence, is what turned the claim on.
  expect(polls).toBeGreaterThanOrEqual(3);
});

test('the billing area survives a 390px phone viewport', async ({ page }) => {
  stubOnly('the layout under test is the stubbed export’s');
  await page.setViewportSize({ width: 390, height: 844 });
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  await page.goto(`/organize/${group.group_id}`);

  await expect(page.getByText('This exchange is on Free')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
