import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Organizer editing and roster management (#135), through the export production builds.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

// ── Appearance ────────────────────────────────────────────────────────────────
//
// The claim is a repaint, so the assertion has to be a colour rather than a
// class or a stored value: the switch is only worth anything if the pixels move.
// The expected values are read from the same JSON the app is built from, so a
// re-brand cannot leave this spec asserting a colour Humbugg no longer uses.

function brandColor(scheme: 'light' | 'dark', role: 'surfaceAlt'): string {
  const file = scheme === 'dark' ? 'brand-colors.dark.json' : 'brand-colors.json';
  const colors = JSON.parse(
    readFileSync(path.join(__dirname, '..', 'src', 'theme', file), 'utf8'),
  ) as Record<string, string>;
  const hex = colors[role]!.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16));
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * The painted colour behind the Appearance control.
 *
 * The first element from the group up that actually paints — the group's own
 * `surfaceAlt` trough today, the `Card` behind it if that trough ever goes
 * away. Walking rather than naming one keeps the spec off layout detail it has
 * no business pinning: every wrapper react-native-web emits is transparent, and
 * either answer is a scheme-dependent colour that has to move.
 */
async function surfaceColor(page: Page): Promise<string> {
  return page.evaluate(() => {
    let element = document.querySelector<HTMLElement>('[role="group"][aria-label="Appearance"]');
    while (element) {
      const background = getComputedStyle(element).backgroundColor;
      if (background && background !== 'rgba(0, 0, 0, 0)' && background !== 'transparent') {
        return background;
      }
      element = element.parentElement;
    }
    return 'nothing paints';
  });
}

test('the appearance choice repaints the app and outlives a reload', async ({ page }) => {
  stubOnly('the same control on a live stack, but the stored key is the browser’s either way');
  await page.emulateMedia({ colorScheme: 'light' });
  await stubApi(page);
  await signIn(page);

  await page.goto('/settings');
  const appearance = page.getByRole('group', { name: 'Appearance' });
  await expect(appearance).toBeVisible();
  expect(await surfaceColor(page)).toBe(brandColor('light', 'surfaceAlt'));

  // Instantly, with no reload — the assertion is only the colour, so a repaint
  // that needed a round trip would fail here rather than pass slowly.
  await page.getByRole('button', { name: 'Dark', exact: true }).click();
  await expect.poll(() => surfaceColor(page)).toBe(brandColor('dark', 'surfaceAlt'));
  await expect(page.getByRole('button', { name: 'Dark', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  // The key, and the app on the other side of a reload.
  expect(await page.evaluate(() => window.localStorage.getItem('humbugg.theme'))).toBe('dark');
  await page.reload();
  await expect(page.getByRole('group', { name: 'Appearance' })).toBeVisible();
  await expect.poll(() => surfaceColor(page)).toBe(brandColor('dark', 'surfaceAlt'));
});

test('System hands the app back to the device, and the key with it', async ({ page }) => {
  stubOnly('the same control on a live stack, but the stored key is the browser’s either way');
  await page.emulateMedia({ colorScheme: 'dark' });
  await stubApi(page);
  await signIn(page);

  await page.goto('/settings');
  await expect(page.getByRole('group', { name: 'Appearance' })).toBeVisible();

  // Force light against a dark device first, so "follows the device" is a change
  // rather than a coincidence.
  await page.getByRole('button', { name: 'Light', exact: true }).click();
  await expect.poll(() => surfaceColor(page)).toBe(brandColor('light', 'surfaceAlt'));

  await page.getByRole('button', { name: 'System', exact: true }).click();
  await expect.poll(() => surfaceColor(page)).toBe(brandColor('dark', 'surfaceAlt'));
  // System is the absence of a stored preference, not a third stored value.
  expect(await page.evaluate(() => window.localStorage.getItem('humbugg.theme'))).toBeNull();

  // And it keeps following: the device changes its mind, the app follows without
  // anybody touching the control.
  await page.emulateMedia({ colorScheme: 'light' });
  await expect.poll(() => surfaceColor(page)).toBe(brandColor('light', 'surfaceAlt'));
});

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
