import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface Group {
  group_id: string;
  name: string;
}

interface Wish {
  title: string;
}

test('a deep link renders the exchange with its wishlist', async ({ page }) => {
  stubOnly('live dev-stack data is not the fixture’s to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const wishes = fixture<Wish[]>('wishes');
  expect(wishes.length).toBeGreaterThan(0);

  // Straight to the URL — this exercises the static host's SPA fallback as well as
  // the screen, which is exactly what a shared link does in production.
  await page.goto(`/groups/${group.group_id}`);

  await expect(page.getByText(group.name).first()).toBeVisible();
  await expect(page.getByText('The exchange circle')).toBeVisible();
  for (const wish of wishes) {
    await expect(page.getByText(wish.title).first()).toBeVisible();
  }
});
