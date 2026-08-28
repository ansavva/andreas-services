// Records the e2e fixtures from the real dev backend — the ONLY sanctioned way to
// produce a file in e2e/fixtures/. Not curl, for the same reason studio's capture.py
// is not curl: the script scrubs anything volatile or signed and then *asserts* the
// scrub held, so a presigned URL carrying an access key id can never land in git.
//
// A hand-written stub drifts from the API silently and then asserts its own
// imagination; one captured from the thing it stands in for cannot drift without
// somebody re-capturing it.
//
// Usage:
//   humbugg/scripts/dev-up-backend.sh          # the API on :5001
//   npm run e2e:capture                        # from humbugg/app
//
// The script is idempotent: it converges its own seed data (profile, one exchange,
// one wish) on the dev stack before capturing, so a fresh stack works from zero.
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { devTokens } from './dev-session.mjs';

const BASE = process.env.HUMBUGG_E2E_API ?? 'http://127.0.0.1:5001/api';
const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
const EXCHANGE_NAME = 'E2E Fixture Exchange';

const SIGNED = /https?:\/\/[^"\s]*X-Amz-(?:Signature|Credential)[^"\s]*/g;
const INVITE = /#invite=[^"\s]+/g;

function scrub(value) {
  if (typeof value === 'string')
    return value.replaceAll(SIGNED, '/e2e-asset.png').replaceAll(INVITE, '#invite=e2e-invite-secret');
  if (Array.isArray(value)) return value.map(scrub);
  if (value && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, scrub(entry)]));
  return value;
}

function write(name, value) {
  const scrubbed = scrub(value);
  const serialized = JSON.stringify(scrubbed, null, 2);
  if (SIGNED.test(serialized))
    throw new Error(`${name}: a signed URL survived scrubbing — refusing to write.`);
  writeFileSync(path.join(FIXTURES, `${name}.json`), `${serialized}\n`);
  console.log(`captured ${name}.json`);
}

async function main() {
  const { accessToken } = await devTokens();

  const call = async (method, apiPath, body) => {
    const response = await fetch(`${BASE}${apiPath}`, {
      method,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok)
      throw new Error(`${method} ${apiPath} -> ${response.status}: ${await response.text()}`);
    return response.status === 204 ? undefined : response.json();
  };

  try {
    await fetch(`${BASE.replace(/\/api$/, '')}/health`);
  } catch {
    console.error(`No API at ${BASE}. Start it first: humbugg/scripts/dev-up-backend.sh`);
    process.exit(1);
  }

  // ── Converge the seed data ────────────────────────────────────────────────────────
  await call('PUT', '/me', {
    display_name: 'E2E Fixture',
    consent: { version: '2026-01', accepted_at: new Date().toISOString() },
  });
  const existing = (await call('GET', '/groups')).find((group) => group.name === EXCHANGE_NAME);
  const groupId = existing?.group_id
    ?? (await call('POST', '/groups', { name: EXCHANGE_NAME, description: 'Captured for the e2e stub.' })).group_id;
  await call('PATCH', `/groups/${groupId}/members/me`, {
    wishlist: 'Wool socks, a good book',
    avoidances: 'No candles',
  });
  const wishes = await call('GET', `/groups/${groupId}/members/me/wishes`);
  if (!wishes.length)
    await call('POST', `/groups/${groupId}/members/me/wishes`, {
      kind: 'product',
      title: 'Wool socks',
      price_cents: 1999,
    });

  // ── Capture ───────────────────────────────────────────────────────────────────────
  mkdirSync(FIXTURES, { recursive: true });
  write('me', await call('GET', '/me'));
  write('groups', await call('GET', '/groups'));
  write('group', await call('GET', `/groups/${groupId}`));
  write('membership', await call('GET', `/groups/${groupId}/members/me`));
  write('wishes', await call('GET', `/groups/${groupId}/members/me/wishes`));
  write('readiness', await call('GET', `/groups/${groupId}/readiness`));
}

await main();
