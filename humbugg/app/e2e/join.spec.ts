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

  await expect(page.getByText('This invitation link is incomplete or has expired.')).toBeVisible();
});
