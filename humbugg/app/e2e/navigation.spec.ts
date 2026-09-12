import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Where you are is in the address bar (#690).
//
// The exchange page used to hold its tab in React state, seeded once from `?tab=`, so a reload
// landed on the first tab and the browser's back button did nothing between them; and the page
// scrolls inside a React Native ScrollView, so the browser's own scroll restoration never saw it.
// These pin the three things a person expects of a page: reload keeps the tab, back and forward
// move between tabs, and reload keeps the place on the page.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

const group = fixture<{ group_id: string }>('group');

test('each tab is a URL: reload keeps it, back and forward move between them', async ({ page }) => {
  await stubApi(page);
  await signIn(page);

  // The bare group URL settles on a tab rather than staying ambiguous.
  await page.goto(`/groups/${group.group_id}`);
  await page.waitForURL(`**/groups/${group.group_id}/you`);
  await expect(page.getByRole('tab', { name: 'For you', selected: true })).toBeVisible();

  await page.getByRole('tab', { name: 'People' }).click();
  await page.waitForURL(`**/groups/${group.group_id}/people`);
  await expect(page.getByText(/^Everyone \(\d+\)$/)).toBeVisible();

  await page.reload();
  await expect(page.getByRole('tab', { name: 'People', selected: true })).toBeVisible();
  await expect(page.getByText(/^Everyone \(\d+\)$/)).toBeVisible();

  await page.goBack();
  await page.waitForURL(`**/groups/${group.group_id}/you`);
  await expect(page.getByRole('tab', { name: 'For you', selected: true })).toBeVisible();

  await page.goForward();
  await page.waitForURL(`**/groups/${group.group_id}/people`);
  await expect(page.getByRole('tab', { name: 'People', selected: true })).toBeVisible();
});

test('a settings section is a URL of its own', async ({ page }) => {
  await stubApi(page);
  await signIn(page);

  await page.goto(`/groups/${group.group_id}/settings/reminders`);
  await expect(page.getByRole('tab', { name: 'Settings', selected: true })).toBeVisible();
  await expect(page.getByText('Reminders', { exact: true })).toBeVisible();

  await page.getByText('Templates', { exact: true }).click();
  await page.waitForURL(`**/groups/${group.group_id}/settings/templates`);

  // The links minted before sections were routes still land where they meant.
  await page.goto(`/groups/${group.group_id}?tab=draw`);
  await page.waitForURL(`**/groups/${group.group_id}/draw`);
  await expect(page.getByText('Taking part')).toBeVisible();
});

test('reload keeps the place on the page', async ({ page }) => {
  stubOnly('the scroll under test is the stubbed export’s; live adds nothing');
  await stubApi(page);
  await signIn(page);
  // A phone: the wishlist page is long enough to scroll on one.
  await page.setViewportSize({ width: 390, height: 700 });

  await page.goto(`/groups/${group.group_id}/you`);
  await expect(page.getByText('What you would love')).toBeVisible();

  // The page scrolls inside the app's own scroller, not the document.
  const scroller = page.locator('div').filter({ has: page.getByText('What you would love') }).evaluateAll((divs) => {
    const el = divs.find((div) => div.scrollHeight > div.clientHeight + 200 && getComputedStyle(div).overflowY !== 'visible');
    return el ? el.scrollHeight : 0;
  });
  expect(await scroller).toBeGreaterThan(700);

  const offset = () => page.evaluate(() =>
    Math.max(...Array.from(document.querySelectorAll('div')).map((div) => div.scrollTop)),
  );
  await page.mouse.move(195, 400);
  await page.mouse.wheel(0, 600);
  // The wheel scrolls asynchronously; wait for it to land before recording where it landed.
  await expect.poll(offset).toBeGreaterThan(300);
  const before = await offset();

  await page.reload();
  await expect(page.getByText('What you would love')).toBeVisible();
  await expect.poll(offset).toBeGreaterThan(before - 40);
});
