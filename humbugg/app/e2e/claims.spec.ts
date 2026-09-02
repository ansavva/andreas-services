import { expect, test, type Page } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Purchase claims (#130), through the export production builds.
//
// These need a DRAWN exchange with an assignment, which the committed fixture is not — it is
// captured open, because that is the state a fresh dev stack is in. Rather than capture a second
// world, the drawn state is layered on top of the base stub here: Playwright consults the
// last-registered route first, so these overrides win and every other call still answers from the
// shared fixtures.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface Group {
  group_id: string;
}

const WISH = {
  wish_id: 'wish-1',
  kind: 'product',
  title: 'Chef knife',
  price_cents: 2599,
  currency: 'USD',
  quantity: 1,
  priority: 'normal',
  position: 0,
};

/** The drawn world: my exchange has been drawn, and I am giving to Robin. */
async function stubDrawn(page: Page, group: Group): Promise<{ claims: unknown[] }> {
  const claims: unknown[] = [];
  let claim: { state: string; quantity: number; updated_at: string } | null = null;

  const assignment = () => ({
    member_id: 'robin',
    display_name: 'Robin',
    wishlist: 'Wool socks, a good book',
    avoidances: 'No candles',
    address: {},
    wishes: [{ ...WISH, claim }],
  });

  await page.route(`**/api/groups/${group.group_id}/assignment`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(assignment()) }),
  );

  await page.route(`**/api/groups/${group.group_id}/assignment/wishes/*/claim`, (route) => {
    const method = route.request().method();
    if (method === 'PUT') {
      const body = route.request().postDataJSON() as { state: string; quantity?: number };
      claims.push({ method, ...body });
      claim = { state: body.state, quantity: body.quantity ?? 1, updated_at: 'now' };
    } else if (method === 'DELETE') {
      claims.push({ method });
      claim = null;
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(assignment()) });
  });

  await page.route(`**/api/groups/${group.group_id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...fixture('group'), status: 'drawn' }),
    }),
  );

  return { claims };
}

test('the giver marks a gift bought and the list says so', async ({ page }) => {
  stubOnly('a live dev stack has no drawn exchange to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const recorded = await stubDrawn(page, group);

  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('Your secret recipient')).toBeVisible();
  await expect(page.getByText('Chef knife')).toBeVisible();

  await page.getByText('I bought it').click();

  await expect(page.getByText('You bought this')).toBeVisible();
  expect(recorded.claims).toEqual([{ method: 'PUT', state: 'purchased', quantity: 1 }]);
  // Bought is the end of the road: nothing further to mark, only an undo.
  await expect(page.getByText('I bought it')).toBeHidden();
  await expect(page.getByText('Undo')).toBeVisible();
});

test('a claim can be released', async ({ page }) => {
  stubOnly('a live dev stack has no drawn exchange to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const recorded = await stubDrawn(page, group);

  await page.goto(`/groups/${group.group_id}`);
  await page.getByText("I'm getting this").click();
  await expect(page.getByText('You are getting this')).toBeVisible();

  await page.getByText('Undo').click();

  await expect(page.getByText('You are getting this')).toBeHidden();
  expect(recorded.claims).toEqual([
    { method: 'PUT', state: 'planned', quantity: 1 },
    { method: 'DELETE' },
  ]);
});

test('the list says the mark is private, on the giver’s side only', async ({ page }) => {
  stubOnly('the copy under test is the stubbed export’s');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  await stubDrawn(page, group);

  await page.goto(`/groups/${group.group_id}`);

  await expect(page.getByText(/never see it, and it is only for this draw/)).toBeVisible();
  // The owner's own list — the editor further down the same page — offers no such control.
  await expect(page.getByText('Your wishlist', { exact: true })).toBeVisible();
  await expect(page.getByText('I bought it')).toHaveCount(1);
});
