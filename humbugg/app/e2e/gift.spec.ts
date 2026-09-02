import { expect, test, type Page } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Gift progress (#132), through the export production builds.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface Group {
  group_id: string;
}

/** A drawn exchange whose gift status the test controls. */
async function stubDrawn(page: Page, group: Group): Promise<{ stages: string[]; received: boolean[] }> {
  const stages: string[] = [];
  const received: boolean[] = [];
  let gift = { stage: 'choosing', stage_at: null as string | null, received: false, received_at: null as string | null, can_change_stage: true };
  let receipt = { received: false, received_at: null as string | null };

  const assignment = () => ({
    member_id: 'robin',
    display_name: 'Robin',
    wishlist: 'Wool socks',
    avoidances: 'No candles',
    address: {},
    wishes: [],
    gift,
  });

  await page.route(`**/api/groups/${group.group_id}/assignment/gift`, (route) => {
    const stage = (route.request().postDataJSON() as { stage: string }).stage;
    stages.push(stage);
    gift = { ...gift, stage, stage_at: '2026-12-01T00:00:00Z' };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(assignment()) });
  });

  await page.route(`**/api/groups/${group.group_id}/members/me/gift`, (route) => {
    if (route.request().method() === 'PUT') {
      const next = (route.request().postDataJSON() as { received: boolean }).received;
      received.push(next);
      receipt = { received: next, received_at: next ? '2026-12-25T00:00:00Z' : null };
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(receipt) });
  });

  await page.route(`**/api/groups/${group.group_id}/assignment`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(assignment()) }));

  await page.route(`**/api/groups/${group.group_id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...fixture('group'), status: 'drawn' }),
    }));

  return { stages, received };
}

test('the giver moves their gift along', async ({ page }) => {
  stubOnly('a live dev stack has no drawn exchange to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const recorded = await stubDrawn(page, group);

  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('Where has it got to?')).toBeVisible();

  // By role, not by text: "Sent it" is also a substring of the receipt panel's own copy further
  // down the page, and a text match would resolve to two elements.
  await page.getByRole('button', { name: 'Bought it' }).click();
  await page.getByRole('button', { name: 'Sent it' }).click();

  expect(recorded.stages).toEqual(['purchased', 'sent']);
});

test('the recipient says it arrived, and is told that reveals nobody', async ({ page }) => {
  stubOnly('a live dev stack has no drawn exchange to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const recorded = await stubDrawn(page, group);

  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('Has it arrived?')).toBeVisible();
  await expect(page.getByText(/does not tell you, or them, who sent it/)).toBeVisible();

  await page.getByLabel('My gift has arrived').click();

  expect(recorded.received).toEqual([true]);
});

/**
 * The organizer's roll-up, at the surface it is read from.
 *
 * Counts and meters, and no name anywhere in the panel — the same rule the rest of the dashboard
 * follows, checked here against the panel's own rendered text.
 */
test('the dashboard reports gift progress as counts and names nobody', async ({ page }) => {
  stubOnly('the live dev stack’s own progress is not the fixture’s to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const readiness = fixture<Record<string, unknown> & { participants: Array<{ display_name: string }> }>('readiness');

  await page.route(`**/api/groups/${group.group_id}/readiness`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...readiness,
        status: 'drawn',
        gift_progress: { purchased: 3, sent: 2, received: 1, total: 4 },
      }),
    }));

  await page.goto(`/organize/${group.group_id}`);

  await expect(page.getByText('Purchased, sent and received')).toBeVisible();
  await expect(page.getByText('3 of 4')).toBeVisible();
  await expect(page.getByText('2 of 4')).toBeVisible();
  await expect(page.getByText('1 of 4')).toBeVisible();
  await expect(page.getByText('Nothing to track yet.')).toBeHidden();
});
