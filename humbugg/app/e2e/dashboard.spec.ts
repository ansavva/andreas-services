import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface GroupSummary {
  group_id: string;
  name: string;
}

test.beforeEach(async ({ page }) => {
  if (!LIVE) await stubApi(page);
  await signIn(page);
});

test('the dashboard lists the captured exchange with its real count', async ({ page }) => {
  stubOnly('live dev-stack data is not the fixture’s to predict');
  const groups = fixture<GroupSummary[]>('groups');
  const captured = groups.find((group) => group.name === 'E2E Fixture Exchange');
  expect(captured).toBeDefined();

  await page.goto('/');
  await expect(page.getByText('E2E Fixture Exchange')).toBeVisible();
  // The count badge renders groups.length — asserted against the fixture, so a stub
  // that quietly served a different listing would fail here rather than nowhere.
  await expect(page.getByText(String(groups.length), { exact: true }).first()).toBeVisible();
});

test('a group card opens the exchange screen', async ({ page }) => {
  stubOnly('live dev-stack data is not the fixture’s to predict');
  const group = fixture<GroupSummary>('group');

  await page.goto('/');
  await page.getByText('E2E Fixture Exchange').first().click();
  await page.waitForURL(`**/groups/${group.group_id}`);
  await expect(page.getByText('The exchange circle')).toBeVisible();
});
