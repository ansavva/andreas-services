import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// The suite's self-policing tier: these specs assert that the harness itself is honest.
// They are the humbugg mirror of studio's "no request escapes" / "nothing 5xxs" pair —
// without them, a missing fixture is an empty screen and a green assertion about nothing.

// Per-spec, never module-level: a module-level test.skip(LIVE) skips the whole file,
// which is how a suite reports green having run nothing.
function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

test('a seeded session reaches the app rather than the sign-in redirect', async ({ page }) => {
  if (!LIVE) await stubApi(page);
  await signIn(page);
  await page.goto('/');
  // The dashboard's own chrome — not "no sign-in button", which would also pass
  // against an error screen.
  await expect(page.getByText('Your groups')).toBeVisible();
});

test('signed out lands on the hosted sign-in page', async ({ page }) => {
  stubOnly('live mode has a real hosted page; the fake domain only exists in the stubbed export');
  await stubApi(page);
  // No signIn(page): the app must decide to leave for Cognito. The fake hosted domain
  // is intercepted so the navigation resolves instead of failing DNS.
  await page.route('**e2e-fake.auth**', (route) =>
    route.fulfill({ contentType: 'text/html', body: '<title>hosted sign-in</title>' }),
  );
  await page.goto('/');
  await page.waitForURL('**e2e-fake.auth**/oauth2/authorize**');
  expect(page.url()).toContain('client_id=e2e-fake-client');
});

test('no request escapes to the network', async ({ page }) => {
  stubOnly('live mode talks to the dev stack on purpose');
  await stubApi(page);
  await signIn(page);
  // Registered before any navigation, so nothing slips through the gap.
  const escaped: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.protocol === 'data:') return;
    if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') return;
    escaped.push(request.url());
  });

  const group = fixture<{ group_id: string }>('group');
  await page.goto('/');
  await expect(page.getByText('Your groups')).toBeVisible();
  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('The exchange circle')).toBeVisible();

  expect(escaped).toEqual([]);
});

test('nothing 5xxs, so no fixture is missing', async ({ page }) => {
  stubOnly('live-mode responses are the dev backend’s to make');
  await stubApi(page);
  await signIn(page);
  const failures: string[] = [];
  page.on('response', (response) => {
    if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
  });

  const group = fixture<{ group_id: string }>('group');
  await page.goto('/');
  await expect(page.getByText('Your groups')).toBeVisible();
  await page.goto(`/groups/${group.group_id}`);
  await expect(page.getByText('The exchange circle')).toBeVisible();

  expect(failures).toEqual([]);
});
