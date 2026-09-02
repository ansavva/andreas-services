import { expect, test, type Page } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// Anonymous questions (#131), through the export production builds.
//
// Like the claims specs, these layer a DRAWN world over the committed fixture — the captured
// exchange is open, because that is the state a fresh dev stack is in.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

interface Group {
  group_id: string;
}

interface Thread {
  messages: Array<{ message_id: string; author: 'giver' | 'recipient'; body: string; created_at: string }>;
  blocked: boolean;
  can_send: boolean;
  blocked_reason: string | null;
  message_limit: number;
}

function thread(overrides: Partial<Thread> = {}): Thread {
  return { messages: [], blocked: false, can_send: true, blocked_reason: null, message_limit: 50, ...overrides };
}

/** A drawn exchange with both conversations under the test's control. */
async function stubDrawn(
  page: Page,
  group: Group,
  seed: { giver?: Thread; recipient?: Thread } = {},
): Promise<{ asked: string[] }> {
  const asked: string[] = [];
  let giver = seed.giver ?? thread();
  const recipient = seed.recipient ?? thread();

  await page.route(`**/api/groups/${group.group_id}/assignment/questions`, (route) => {
    if (route.request().method() === 'POST') {
      const body = (route.request().postDataJSON() as { body: string }).body;
      asked.push(body);
      giver = thread({
        messages: [...giver.messages, { message_id: `m${giver.messages.length}`, author: 'giver', body, created_at: 'now' }],
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(giver) });
  });

  await page.route(`**/api/groups/${group.group_id}/members/me/questions**`, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(recipient) }),
  );

  await page.route(`**/api/groups/${group.group_id}/assignment`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        member_id: 'robin',
        display_name: 'Robin',
        wishlist: 'Wool socks',
        avoidances: 'No candles',
        address: {},
        wishes: [],
      }),
    }),
  );

  await page.route(`**/api/groups/${group.group_id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...fixture('group'), status: 'drawn' }),
    }),
  );

  return { asked };
}

test('the giver asks anonymously and the question appears as theirs', async ({ page }) => {
  stubOnly('a live dev stack has no drawn exchange to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const recorded = await stubDrawn(page, group);

  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('Ask about their gift')).toBeVisible();

  await page.getByLabel('Ask about their gift').fill('What size do you take?');
  await page.getByText('Send anonymously').click();

  await expect(page.getByText('What size do you take?')).toBeVisible();
  expect(recorded.asked).toEqual(['What size do you take?']);
});

/**
 * The identity guarantee, at the last surface it could leak through.
 *
 * The recipient's panel renders a question with `author: "giver"`. Everything on that screen is
 * checked for the one thing it must never contain: a person. "Your giver" is a role; the roster
 * name of whoever asked appears nowhere.
 */
test('the recipient is never told who asked', async ({ page }) => {
  stubOnly('a live dev stack has no drawn exchange to predict');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  const roster = fixture<{ members: Array<{ display_name: string }> }>('group');
  await stubDrawn(page, group, {
    recipient: thread({
      messages: [{ message_id: 'm1', author: 'giver', body: 'Do you already own it?', created_at: 'now' }],
    }),
  });

  await page.goto(`/groups/${group.group_id}`);

  await expect(page.getByText('Questions about your gift')).toBeVisible();
  await expect(page.getByText('Do you already own it?')).toBeVisible();
  await expect(page.getByText('Your giver').first()).toBeVisible();

  // The panel's own subtree carries no roster name — not the asker's, not anyone's.
  const panel = page.locator('div').filter({ hasText: 'Questions about your gift' }).last();
  const text = (await panel.innerText()).toLowerCase();
  for (const member of roster.members) {
    expect(text).not.toContain(member.display_name.toLowerCase());
  }
});

test('a blocked thread offers the giver no way to send', async ({ page }) => {
  stubOnly('the copy under test is the stubbed export’s');
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  await stubDrawn(page, group, {
    giver: thread({
      blocked: true,
      can_send: false,
      blocked_reason: 'Questions are turned off for this gift.',
    }),
  });

  await page.goto(`/groups/${group.group_id}`);

  await expect(page.getByText('Questions are turned off for this gift.')).toBeVisible();
  await expect(page.getByText('Send anonymously')).toBeHidden();
});

test('the question panels survive a 390px phone viewport', async ({ page }) => {
  stubOnly('the layout under test is the stubbed export’s');
  await page.setViewportSize({ width: 390, height: 844 });
  await stubApi(page);
  await signIn(page);
  const group = fixture<Group>('group');
  await stubDrawn(page, group);

  await page.goto(`/groups/${group.group_id}`);

  await expect(page.getByText('Ask about their gift')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
