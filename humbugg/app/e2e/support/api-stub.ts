import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Page } from '@playwright/test';

const FIXTURES = path.join(__dirname, '..', 'fixtures');

// `readFileSync`, not `import ... from "*.json"`: these are captured artefacts, not
// modules, and reading them off disk keeps them re-recordable without a rebuild.
export function fixture<T = unknown>(name: string): T {
  return JSON.parse(readFileSync(path.join(FIXTURES, `${name}.json`), 'utf8')) as T;
}

function json(body: unknown): { status: number; contentType: string; body: string } {
  return { status: 200, contentType: 'application/json', body: JSON.stringify(body) };
}

/**
 * One dispatcher over every `/api/**` request, answering from the committed fixtures.
 *
 * An unrecognised path is a 501 carrying the path in the body — never `{}`. A stub that
 * quietly returns an empty object turns a missing fixture into an empty screen and an
 * assertion about nothing; a 501 says exactly which fixture to capture, and the
 * "nothing 5xxs" guard spec turns it into a hard failure.
 */
export async function stubApi(page: Page): Promise<void> {
  const group = fixture<{ group_id: string }>('group');

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;

    if (p === '/api/me') return route.fulfill(json(fixture('me')));
    if (p === '/api/groups') return route.fulfill(json(fixture('groups')));
    if (p === `/api/groups/${group.group_id}`) return route.fulfill(json(fixture('group')));
    if (p === `/api/groups/${group.group_id}/members/me`)
      return route.fulfill(json(fixture('membership')));
    if (p === `/api/groups/${group.group_id}/members/me/wishes`)
      return route.fulfill(json(fixture('wishes')));
    if (p === `/api/groups/${group.group_id}/readiness`)
      return route.fulfill(json(fixture('readiness')));
    if (p === `/api/groups/${group.group_id}/invitation`)
      return route.fulfill(json(fixture('invitation')));

    return route.fulfill({
      status: 501,
      contentType: 'application/json',
      body: JSON.stringify({
        error: { code: 'e2e_unstubbed', message: `no fixture for ${route.request().method()} ${p}` },
      }),
    });
  });
}
