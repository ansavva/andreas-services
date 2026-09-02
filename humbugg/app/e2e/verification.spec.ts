import { expect, test } from '@playwright/test';
import { fixture, stubApi } from './support/api-stub';
import { LIVE, signIn } from './support/auth';

// The mechanical half of #138 — "verify the complete Free exchange on mobile and assistive
// technology". The flows themselves are covered screen by screen in the other specs; what is here
// is the part no single-screen spec looks at: that every primary screen survives a narrow phone,
// that the keyboard alone reaches the work, and that private information stays off the surfaces it
// has no business on.
//
// The manual half — a real screen reader, real gesture navigation, real reduced motion — is
// `docs/free-verification-checklist.md`. This file is deliberately the part a machine can hold, so
// that the checklist stays short enough that somebody actually runs it.

function stubOnly(reason: string): void {
  test.skip(LIVE, reason);
}

const group = fixture<{ group_id: string }>('group');

/** Every screen a Free participant or organizer reaches, and how to know it rendered. */
const SCREENS: Array<{ path: string; heading: string }> = [
  { path: '/', heading: 'Your groups' },
  { path: `/groups/${group.group_id}`, heading: 'The exchange circle' },
  { path: `/organize/${group.group_id}`, heading: 'Who is ready' },
  // Not reached by any other spec, which is how it came to be the one screen with no coverage.
  { path: '/settings', heading: 'Your account' },
];

/**
 * The widths a phone actually is.
 *
 * 320 is the narrowest viewport still in use (an SE in landscape-locked apps, and the width iOS
 * reports at the largest accessibility text sizes); 390 is the modern default; 414 is the "plus"
 * class. A layout that holds at 320 holds everywhere, so that is the one that earns its place.
 */
const WIDTHS = [320, 390, 414];

for (const { path, heading } of SCREENS) {
  for (const width of WIDTHS) {
    test(`${path} fits a ${width}px phone`, async ({ page }) => {
      if (!LIVE) await stubApi(page);
      await signIn(page);
      await page.setViewportSize({ width, height: 780 });
      await page.goto(path);
      await expect(page.getByText(heading).first()).toBeVisible();

      // Horizontal overflow is the mobile failure that survives every desktop review: the page
      // still "works", it just slides sideways under the thumb and clips whatever is on the right.
      // One pixel of slack absorbs sub-pixel rounding in the layout engine.
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return Math.max(doc.scrollWidth, document.body.scrollWidth) - doc.clientWidth;
      });
      expect(overflow).toBeLessThanOrEqual(1);
    });
  }
}

/**
 * The work is reachable with the keyboard alone.
 *
 * This is the check that matters for a switch device and for anybody not using a pointer. It walks
 * `Tab` the way a person would and collects what each stop announces itself as — so a control that
 * is focusable but nameless fails here as an empty string, and a control that is unreachable fails
 * by never appearing.
 */
test('the dashboard is reachable and named, by keyboard alone', async ({ page }) => {
  if (!LIVE) await stubApi(page);
  await signIn(page);
  await page.goto('/');
  await expect(page.getByText('Your groups')).toBeVisible();

  const stops: string[] = [];
  for (let step = 0; step < 25; step++) {
    await page.keyboard.press('Tab');
    const stop = await page.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      if (!active || active === document.body) return null;
      const name =
        active.getAttribute('aria-label') ??
        active.getAttribute('title') ??
        active.textContent?.trim() ??
        '';
      return { name, tag: active.tagName, tabIndex: active.tabIndex };
    });
    if (!stop) continue;
    // A positive tabIndex reorders the whole page's tab sequence relative to everything that does
    // not have one, which is a defect wherever it appears rather than a preference.
    expect(stop.tabIndex).toBeLessThanOrEqual(0);
    if (stop.name) stops.push(stop.name);
  }

  // The exchange has to be openable without a pointer; it is the only way off this screen.
  expect(stops.join(' | ')).toContain('E2E Fixture Exchange');
  // Nothing focusable may be anonymous.
  expect(stops.filter((name) => name.length === 0)).toEqual([]);
});

/**
 * Private information stays out of the console.
 *
 * A `console.log(response)` left in an error path is the cheapest way to put a wishlist into a
 * browser extension's reach, and it survives review because nothing renders differently.
 */
test('no wishlist, address or token reaches the console', async ({ page }) => {
  stubOnly('live console output is the dev backend’s to make, and carries real data by design');
  await stubApi(page);
  await signIn(page);

  const said: string[] = [];
  page.on('console', (message) => said.push(message.text()));
  page.on('pageerror', (error) => said.push(String(error)));

  for (const { path, heading } of SCREENS) {
    await page.goto(path);
    await expect(page.getByText(heading).first()).toBeVisible();
  }

  const transcript = said.join('\n');
  for (const secret of ['Wool socks', 'No candles', 'humbugg.auth.accessToken', 'e2e-refresh-token'])
    expect(transcript).not.toContain(secret);
});

/**
 * The signed-out invitation page shows an exchange's name and nothing else about it.
 *
 * This is the only screen an unauthenticated stranger can render with a real group id, so it is the
 * only place where "what does the API return" and "who is asking" can come apart. The preview
 * endpoint is deliberately a different, smaller shape than the group — the check is that the
 * SCREEN has nothing more than that shape carries, including in markup a reader never sees.
 */
test('the signed-out invitation exposes the name and nothing more', async ({ page }) => {
  stubOnly('the fixture is the assertion here; live data is the dev stack’s');
  await stubApi(page);
  // Deliberately no signIn: this is what a stranger with the link renders.
  await page.goto(`/join/${group.group_id}#invite=e2e-invite-secret`);
  await expect(page.getByText('E2E Fixture Exchange')).toBeVisible();

  const markup = await page.content();
  for (const secret of [
    'Wool socks', // a wishlist
    'No candles', // an avoidance
    'e284c1d4f6e66e451f520c63869861ef', // a member id
    'Captured for the e2e stub.', // the group's description, which the preview omits
  ])
    expect(markup).not.toContain(secret);
});

/**
 * The invite secret stays in the fragment, and the fragment never leaves the browser.
 *
 * `#invite=` rather than `?invite=` is the whole reason the token is safe to put in a link people
 * paste into chat apps: a fragment is not sent to the server, so it cannot reach an access log, a
 * proxy, or a `Referer` header. A refactor to a query parameter would look identical on screen.
 */
test('the invite secret is never put on the wire as a query parameter', async ({ page }) => {
  stubOnly('asserts the stubbed export’s own request shape');
  await stubApi(page);

  const urls: string[] = [];
  page.on('request', (request) => urls.push(request.url()));

  await page.goto(`/join/${group.group_id}#invite=e2e-invite-secret`);
  await expect(page.getByText('E2E Fixture Exchange')).toBeVisible();

  expect(urls.filter((url) => url.includes('e2e-invite-secret'))).toEqual([]);
});

/**
 * A Free exchange is told what Plus would add, rather than shown a form that can only fail (#574).
 *
 * The captured fixture group is on Free, so the API really does answer 402 here. What this pins is
 * that the screen treats that as the ANSWER — an upgrade offer — rather than as an error, which is
 * the difference between a plan boundary and a broken page.
 */
test('every Plus capability offers Plus on a Free exchange instead of failing', async ({ page }) => {
  stubOnly('the dev stack’s own plan decides this in live mode');
  await stubApi(page);
  await signIn(page);

  await page.goto(`/organize/${group.group_id}`);
  await expect(page.getByText('Sending and tracking invitations is part of Plus.')).toBeVisible();
  await expect(page.getByText('Automatic reminders are part of Plus.')).toBeVisible();
  // No dead forms behind the notices.
  await expect(page.getByLabel('Email addresses')).toBeHidden();
  await expect(page.getByLabel('How often, in days')).toBeHidden();

  // One purchase, one place to make it. A locked notice that carried its own checkout button would
  // put several on this page — which is how `billing.spec.ts` caught the first attempt.
  await expect(page.getByText('$12 once, for this exchange')).toBeVisible();
});
