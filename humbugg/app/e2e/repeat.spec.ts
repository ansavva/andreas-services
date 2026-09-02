import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Repeating an exchange (#136), through the export production builds.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface Group {
  group_id: string;
}

test('an owner starts next year’s exchange and gets its one-time link', async ({ page }) => {
  stubOnly('a live dev stack has no drawn exchange to repeat');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const sent: Array<Record<string, unknown>> = [];

  await page.route(`**/api/groups/${group.group_id}/repeat`, (route) => {
    sent.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        group: { ...fixture('group'), group_id: 'g2', name: 'Office Exchange 2027', status: 'open' },
        invite_url: 'https://app.humbugg.com/join/g2#invite=secret',
        prior_participants: ['Robin'],
      }),
    });
  });
  await page.route(`**/api/groups/${group.group_id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...fixture('group'), status: 'drawn' }),
    }));
  await page.route(`**/api/groups/${group.group_id}/assignment`, (route) =>
    route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: { code: 'not_found', message: 'none' } }) }));

  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('Run this exchange again')).toBeVisible();
  // The promise, made before anything is pressed.
  await expect(page.getByText(/This one is left exactly as it is/)).toBeVisible();

  await page.getByRole('button', { name: 'Set up next year' }).click();
  await page.getByLabel('Name the new exchange').fill('Office Exchange 2027');
  await page.getByRole('button', { name: 'Create it' }).click();

  await expect(page.getByText('Office Exchange 2027 is set up')).toBeVisible();
  await expect(page.getByText(/Nobody has been added/)).toBeVisible();
  // Last year's roster, as a reminder of who to send to.
  await expect(page.getByText('Robin')).toBeVisible();

  // Exclusions are opt-in; details are not.
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatchObject({ copy_details: true, copy_exclusions: false });
});

test('the repeat panel is not offered before the draw', async ({ page }) => {
  stubOnly('the stubbed fixture is the exchange under test');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');

  // The committed fixture is open, which is the state under test.
  await page.goto(`/groups/${group.group_id}`);

  await expect(page.getByText('The exchange circle')).toBeVisible();
  await expect(page.getByText('Run this exchange again')).toBeHidden();
});
