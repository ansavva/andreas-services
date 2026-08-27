/**
 * A signed-in browser, without Cognito and without a backdoor in the app.
 *
 * `App.tsx` redirects to Cognito Managed Login unless `authenticated`, and
 * `authenticated` is whether `auth/oauth.ts` finds an ID token. Three ways to
 * get past that were considered:
 *
 *   1. Drive the hosted sign-in page. It is a real Cognito page on a real
 *      domain; a stubbed browser cannot reach it and a live one needs an
 *      account, a pool and credentials this workflow deliberately does not
 *      have.
 *   2. Add `if (import.meta.env.VITE_E2E) authenticated = true`. That is a
 *      test backdoor compiled into the production bundle. No.
 *   3. Seed the token store the app itself reads. That is this file.
 *
 * **This got simpler when Amplify went.** The store used to be Amplify's five
 * `CognitoIdentityServiceProvider.<clientId>.<user>.<field>` keys, seeded in a
 * shape only Amplify's reader understood. It is now one JSON blob under one
 * key — the same one `handleCallback` writes — so what is being faked is
 * visible rather than reverse-engineered.
 *
 * Nothing verifies the signature in the browser — it cannot, it has no key —
 * so an unsigned JWT with a distant `exp` is accepted exactly as a real one
 * is, and no token endpoint is ever called while it is unexpired.
 *
 * The token never reaches a server: every `/api/**` request is fulfilled by
 * `stubApi`. In LIVE mode this file is not used at all — see `live.ts`.
 */
import type { Page } from "@playwright/test";

/** Base64url without padding, which is what a JWT segment is. */
function segment(value: object): string {
  return Buffer.from(JSON.stringify(value))
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

//: A pool, client and managed-login host that do not exist and are never
//: contacted.
//:
//: **The app has to be CONFIGURED, not absent.** Building with the Cognito
//: variables empty makes `isAuthConfigured()` false, and the app then renders
//: "Auth is not configured — set VITE_COGNITO_CLIENT_ID..." rather than
//: attempting a session. A first attempt asserted "no sign-in button is
//: visible" against that screen and passed, which is the shape of a test that
//: proves nothing.
//:
//: `VITE_COGNITO_DOMAIN` is included for the same reason: without it the app
//: is unconfigured even with a client id, because there is nowhere to redirect
//: to. It is never resolved — the seeded token means no leg of the OAuth flow
//: runs.
export const POOL_ID = "us-east-1_e2etestpool";
export const CLIENT_ID = "e2eclientid0000000000000";
export const AUTH_DOMAIN = "studio-e2e.auth.us-east-1.amazoncognito.com";
export const EMAIL = "e2e@studio.test";

/** A structurally valid, deliberately unsigned JWT. */
export function fakeIdToken(): string {
  const now = Math.floor(Date.now() / 1000);
  const header = segment({ alg: "RS256", kid: "e2e", typ: "JWT" });
  const payload = segment({
    sub: "00000000-0000-0000-0000-00000000e2e0",
    email: EMAIL,
    aud: CLIENT_ID,
    token_use: "id",
    iss: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_e2etestpool",
    iat: now,
    // Far enough out that a renewal is never attempted mid-run. The client
    // only reaches the token endpoint after a 401, and the stub never sends
    // one.
    exp: now + 60 * 60 * 24,
  });
  return `${header}.${payload}.e2e-not-a-real-signature`;
}

/**
 * Write the session before any application script runs.
 *
 * `addInitScript` runs on every navigation in the context, which matters: a
 * reload must find the session too, or half these specs would find themselves
 * redirected to a Cognito domain that does not exist.
 */
export async function signIn(page: Page, library: string): Promise<void> {
  const token = fakeIdToken();
  await page.addInitScript(
    ([idToken, lib]) => {
      // The exact shape `auth/oauth.ts` writes in `handleCallback` and reads
      // in `getTokens`. One key, one JSON object.
      window.localStorage.setItem(
        "studio.auth.tokens",
        JSON.stringify({
          idToken,
          accessToken: idToken,
          refreshToken: "e2e-refresh",
          expiresAt: Date.now() + 24 * 60 * 60 * 1000,
        }),
      );
      // `LibraryContext` mirrors the chosen library here, so a run starts where
      // a returning user would rather than on the switcher.
      window.localStorage.setItem("studio.library", lib);
    },
    [token, library] as const,
  );
}
