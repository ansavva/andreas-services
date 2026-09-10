import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { LIVE } from './support/auth';

// #373 — proves a real sign-in produces a token the API actually accepts. Every other
// spec in this suite seeds tokens straight into the app's own store (support/auth.ts)
// and never calls the backend directly with them; this is the one place that does.
//
// Live tier only (E2E_LIVE=1): a stubbed run has no dev-stack account to sign in as.
// Per-spec skip, never module-level (TESTING.md rule #6) — a module-level
// `test.skip(!LIVE)` would skip the whole file and report green having run nothing.
function liveOnly(reason: string): void {
  test.skip(!LIVE, reason);
}

const API_BASE_URL = 'http://127.0.0.1:5001/api';

// Minted once by globalSetup (support/live-setup.mjs) via a real SRP sign-in against
// this machine's dev Cognito pool (support/dev-session.mjs) and parked here. Reading
// the file rather than calling devTokens() again keeps this spec to the one sign-in
// the whole live run already pays for.
const LIVE_SESSION = path.join(__dirname, 'support', '.live-session.json');

interface LiveTokens {
  accessToken: string;
  idToken: string;
  refreshToken: string;
}

function liveTokens(): LiveTokens {
  return JSON.parse(readFileSync(LIVE_SESSION, 'utf8')) as LiveTokens;
}

/** Decodes a JWT's payload without checking its signature — plenty to read `sub`. */
function decodeJwtPayload(token: string): Record<string, unknown> {
  const payload = token.split('.')[1];
  return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as Record<string, unknown>;
}

test('a real access token reaches /api/me, and the profile is the same account', async ({ request }) => {
  liveOnly('there is no dev-stack account to sign in as outside the live tier');
  const { accessToken } = liveTokens();
  const sub = decodeJwtPayload(accessToken).sub as string;

  const response = await request.get(`${API_BASE_URL}/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  expect(response.status()).toBe(200);
  const body = (await response.json()) as { user_id: string };
  expect(body.user_id).toBe(sub);
});

// The one check nothing else in the repo can make. A hand-built ClaimsPrincipal in a
// unit test can assert whatever claims it likes; it cannot produce a real, signed ID
// token and watch the API tell it apart from an access token. `Program.cs`'s
// `OnTokenValidated` rejects any token whose `token_use` isn't `"access"` (and whose
// `client_id` doesn't match) via `context.Fail(...)`, which routes to the same
// `OnChallenge` a missing token hits — so an ID token and no token both come back 401,
// not because nobody checked it but because both fail the same access-token test.
test('an ID token is not an access token, and the API says so', async ({ request }) => {
  liveOnly('there is no dev-stack account to sign in as outside the live tier');
  const { idToken } = liveTokens();

  const response = await request.get(`${API_BASE_URL}/me`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });

  expect(response.status()).toBe(401);
});

test('no token, no entry', async ({ request }) => {
  liveOnly('there is no dev-stack account to sign in as outside the live tier');

  const response = await request.get(`${API_BASE_URL}/me`);

  expect(response.status()).toBe(401);
});
