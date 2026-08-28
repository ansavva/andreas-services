import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import type { Page } from '@playwright/test';

export const LIVE = process.env.E2E_LIVE === '1';

// The e2e session is seeded by writing the token store the app itself reads on start —
// the exact localStorage keys `src/auth/oauth.ts` writes in `handleCallback` and reads
// in `loadTokens`. Three approaches were on the table; the other two lost:
//  - driving the hosted Cognito page: unreachable in stubbed mode by design;
//  - an `if (E2E) authenticated = true` switch: a test backdoor compiled into the
//    production bundle. No.
//
// The stubbed tokens are structurally valid, deliberately unsigned JWTs. The app never
// verifies signatures (every authorization decision is the backend's), and with
// `expiresAt` in the future no token endpoint is ever called.
function base64url(value: object): string {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function unsignedJwt(payload: Record<string, unknown>): string {
  return `${base64url({ alg: 'none', typ: 'JWT' })}.${base64url(payload)}.`;
}

const HERE = __dirname;
const LIVE_SESSION = path.join(HERE, '.live-session.json');

interface SeedTokens {
  accessToken: string;
  refreshToken: string;
  idToken: string;
}

function tokens(): SeedTokens {
  if (LIVE) {
    // Minted by live-setup.mjs from the dev-user.sh account via real SRP.
    if (!existsSync(LIVE_SESSION))
      throw new Error('live session missing — did globalSetup run? (E2E_LIVE=1 sets it up)');
    return JSON.parse(readFileSync(LIVE_SESSION, 'utf8')) as SeedTokens;
  }
  const exp = Math.floor(Date.now() / 1000) + 24 * 60 * 60;
  return {
    accessToken: unsignedJwt({ sub: 'e2e-user', token_use: 'access', exp }),
    refreshToken: 'e2e-refresh-token',
    idToken: unsignedJwt({ sub: 'e2e-user', email: 'e2e@humbugg.test', exp }),
  };
}

/** Seeds the app's own token store before any page script runs; survives reloads. */
export async function signIn(page: Page): Promise<void> {
  const seed = tokens();
  await page.addInitScript((session: SeedTokens) => {
    window.localStorage.setItem('humbugg.auth.accessToken', session.accessToken);
    window.localStorage.setItem('humbugg.auth.refreshToken', session.refreshToken);
    window.localStorage.setItem('humbugg.auth.idToken', session.idToken);
    window.localStorage.setItem('humbugg.auth.expiresAt', String(Date.now() + 60 * 60 * 1000));
  }, seed);
}
