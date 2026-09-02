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

interface Readiness {
  requires_address: boolean;
  counts: { members: number; participating: number; wishlist_ready: number; needs_nudge: number };
  participants: Array<{ display_name: string }>;
}

test('the organizer reaches the readiness dashboard from the exchange', async ({ page }) => {
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  await page.goto(`/groups/${group.group_id}`);
  await page.getByText('See who is ready →').click();

  await expect(page.getByText('Who is ready', { exact: true })).toBeVisible();
  await expect(page.getByText('Organizer dashboard')).toBeVisible();
});

test('a deep link to the dashboard renders the roll-up and the roster', async ({ page }) => {
  stubOnly('live dev-stack readiness is not the fixture’s to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const readiness = fixture<Readiness>('readiness');

  // Straight to the URL, so this exercises the static host's SPA fallback for a nested
  // route as well as the screen itself.
  await page.goto(`/organize/${group.group_id}`);

  await expect(page.getByText('Who is ready', { exact: true })).toBeVisible();
  await expect(page.getByText('Taking part')).toBeVisible();
  await expect(page.getByText('The full roster')).toBeVisible();
  for (const person of readiness.participants) {
    await expect(page.getByText(person.display_name).first()).toBeVisible();
  }
  await expect(
    page.getByText(`${readiness.counts.wishlist_ready} of ${readiness.counts.participating}`).first(),
  ).toBeVisible();
});

test('gift progress reads as untracked rather than as zero', async ({ page }) => {
  stubOnly('the live dev stack’s own progress is not the fixture’s to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  await page.goto(`/organize/${group.group_id}`);

  // The fixture exchange is open, so nobody has been asked to buy anything. The dashboard says so
  // rather than reporting zero purchases, which would be a claim about the world.
  await expect(page.getByText('Nothing to track yet.')).toBeVisible();
});

test('the dashboard survives a 390px phone viewport', async ({ page }) => {
  stubOnly('live dev-stack readiness is not the fixture’s to predict');
  await page.setViewportSize({ width: 390, height: 844 });
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  await page.goto(`/organize/${group.group_id}`);

  await expect(page.getByText('Who is ready', { exact: true })).toBeVisible();
  await expect(page.getByText('The full roster')).toBeVisible();
  // Nothing overflows the viewport — a stat tile that does not reflow is the failure this catches.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
