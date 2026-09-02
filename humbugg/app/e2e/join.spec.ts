import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

interface Group {
  group_id: string;
}

// Both specs run in live mode too: the join screen reads the secret from the URL
// fragment and calls nothing until the button is pressed, so live adds no dependency
// beyond the dev server itself.

test.beforeEach(async ({ page }) => {
  if (!LIVE) await stubApi(page);
  await signIn(page);
});

test('an invitation link offers the join action', async ({ page }) => {
  const group = fixture<Group>('group');

  // The secret rides the URL fragment, never the query string — it must not reach
  // servers or logs. The screen reads it from location.hash on load.
  await page.goto(`/join/${group.group_id}#invite=e2e-invite-secret`);

  await expect(page.getByText(/You(’|')re invited/)).toBeVisible();
  await expect(page.getByRole('button', { name: /join/i })).toBeEnabled();
});

test('a link without its secret says so instead of failing silently', async ({ page }) => {
  const group = fixture<Group>('group');

  await page.goto(`/join/${group.group_id}`);

  await expect(page.getByText(/This invitation link is incomplete/)).toBeVisible();
});

/**
 * The exchange is named before anybody is asked to join it, and the secret reaches the preview in a
 * HEADER (#134).
 *
 * Both halves are regressions waiting to happen. The preview endpoint sat uncalled for months, and
 * when it was called it used a relative `/api` path that stopped resolving the day the app moved to
 * its own origin. And the secret used to travel as `?invite_token=`, which API Gateway and
 * CloudFront both write to an access log — the exact leak the URL fragment exists to prevent.
 */
test('the invitation names the exchange, and the secret travels in a header', async ({ page }) => {
  test.skip(LIVE, 'the live dev stack’s invitation is not the fixture’s to predict');
  const group = fixture<Group>('group');
  const seen: Array<{ url: string; invite: string | undefined }> = [];

  await page.route(`**/api/groups/${group.group_id}/invitation`, (route) => {
    seen.push({
      url: route.request().url(),
      invite: route.request().headers()['x-humbugg-invite'],
    });
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ group_id: group.group_id, exchange_name: 'Office Exchange', customization: {} }),
    });
  });

  await page.goto(`/join/${group.group_id}#invite=e2e-invite-secret`);

  await expect(page.getByText('Office Exchange')).toBeVisible();
  expect(seen).toHaveLength(1);
  expect(seen[0].invite).toBe('e2e-invite-secret');
  // Not in the URL. This is the assertion that would catch somebody "simplifying" it back.
  expect(seen[0].url).not.toContain('e2e-invite-secret');
  expect(seen[0].url).not.toContain('invite_token');
});

test('a signed-out visitor is told about the account before pressing anything', async ({ page }) => {
  test.skip(LIVE, 'live mode is signed in by design');
  const group = fixture<Group>('group');
  // Drop the seeded session: this is the state a real invitee arrives in.
  await page.addInitScript(() => window.localStorage.clear());

  await page.goto(`/join/${group.group_id}#invite=e2e-invite-secret`);

  await expect(page.getByText(/You need a free Humbugg account/)).toBeVisible();
  await expect(page.getByRole('button', { name: /Sign in or create an account/ })).toBeVisible();
});
