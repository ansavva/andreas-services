import { expect, test, type Page } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Organizer editing and roster management (#135), through the export production builds.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface Group {
  group_id: string;
  updated_at: string;
}

/** Records what the edit form sends, and lets a test make the save conflict. */
async function stubEditing(page: Page, group: Group, options: { conflict?: boolean } = {}) {
  const saves: Array<Record<string, unknown>> = [];
  await page.route(`**/api/groups/${group.group_id}`, (route) => {
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      saves.push(body);
      if (options.conflict) {
        return route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: { code: 'conflict', message: 'Somebody else changed this exchange.' },
          }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...fixture('group'), ...body }),
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('group')) });
  });
  return { saves };
}

test('the organizer edits the exchange and the save carries its concurrency token', async ({ page }) => {
  stubOnly('a live dev stack’s exchange is not the fixture’s to rewrite');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const recorded = await stubEditing(page, group);

  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('Exchange details')).toBeVisible();

  await page.getByLabel('How it works (optional)').fill('Bring it wrapped to the Friday lunch.');
  await page.getByRole('button', { name: 'Save changes' }).click();

  await expect(page.getByText('Saved.')).toBeVisible();
  expect(recorded.saves).toHaveLength(1);
  expect(recorded.saves[0]).toMatchObject({
    instructions: 'Bring it wrapped to the Friday lunch.',
    // The token the form loaded with. Without it the save is last-write-wins.
    expected_updated_at: group.updated_at,
  });
});

/**
 * The conflict, at the surface the organizer meets it.
 *
 * A 409 here is not a failure to retry — retrying a stale save fails identically — so the copy has
 * to name the one thing that resolves it.
 */
test('a save that lost the race says to reload rather than to try again', async ({ page }) => {
  stubOnly('the copy under test is the stubbed export’s');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  await stubEditing(page, group, { conflict: true });

  await page.goto(`/groups/${group.group_id}`);
  await page.getByLabel('Description (optional)').fill('Rewritten.');
  await page.getByRole('button', { name: 'Save changes' }).click();

  await expect(page.getByText(/Reload the page to see their version/)).toBeVisible();
  await expect(page.getByText('Saved.')).toBeHidden();
});

/**
 * Read as a PARTICIPANT, which is the claim: the instructions are for everybody who joined, not for
 * the person who wrote them. It also keeps the assertion unambiguous — an organizer sees the same
 * text twice, once in the panel and once loaded into the edit form's textarea.
 */
test('the organizer’s instructions are shown to everybody who joined', async ({ page }) => {
  stubOnly('a live dev stack has no instructions to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  await page.route(`**/api/groups/${group.group_id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...fixture('group'),
        is_organizer: false,
        is_owner: false,
        instructions: 'Bring it wrapped to the Friday lunch.',
      }),
    }));

  await page.goto(`/groups/${group.group_id}`);

  await expect(page.getByText('How this one works')).toBeVisible();
  await expect(page.getByText('Bring it wrapped to the Friday lunch.')).toBeVisible();
  // And a participant is not offered the editor.
  await expect(page.getByText('Exchange details')).toBeHidden();
});

/**
 * Removal is armed before it commits — the same shape the delete and clear controls use.
 *
 * It takes the person's wishlist, purchase claims, conversations and gift progress with them, so a
 * stray tap must not do it.
 */
test('removing a participant takes two presses', async ({ page }) => {
  stubOnly('a live dev stack’s roster is not the fixture’s to change');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const removals: string[] = [];

  await page.route(`**/api/groups/${group.group_id}/members/*`, (route) => {
    if (route.request().method() === 'DELETE') {
      removals.push(new URL(route.request().url()).pathname);
      return route.fulfill({ status: 204, body: '' });
    }
    return route.fallback();
  });
  await page.route(`**/api/groups/${group.group_id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...fixture('group'),
        members: [
          ...fixture<{ members: unknown[] }>('group').members,
          { member_id: 'm2', display_name: 'Robin', is_organizer: false, is_participating: true },
        ],
      }),
    }));

  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('Robin')).toBeVisible();

  await page.getByLabel('Remove Robin').click();
  expect(removals).toEqual([]);

  await page.getByLabel('Confirm removing Robin').click();
  expect(removals).toEqual([`/api/groups/${group.group_id}/members/m2`]);
});
