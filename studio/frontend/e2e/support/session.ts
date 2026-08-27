/**
 * A signed-in browser, without Cognito and without a backdoor in the app.
 *
 * `App.tsx` renders `<LoginForm />` unless `authenticated`, and `authenticated`
 * comes from Amplify. Three ways to get past that were considered:
 *
 *   1. Stub the Cognito endpoint. SRP is a multi-round-trip proof; faking it
 *      convincingly is not realistic.
 *   2. Add `if (import.meta.env.VITE_E2E) authenticated = true`. That is a
 *      test backdoor compiled into the production bundle. No.
 *   3. Seed the token store Amplify itself reads. That is this file.
 *
 * Amplify v6 keeps tokens in `localStorage` under
 * `CognitoIdentityServiceProvider.<clientId>.<user>.<field>` and returns the id
 * token from `fetchAuthSession()` without a network call while it is unexpired.
 * It does not verify the signature in the browser — it cannot, it has no key —
 * so an unsigned JWT with a distant `exp` is accepted exactly as a real one is.
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

//: A pool that does not exist and is never contacted.
//:
//: **Amplify has to be CONFIGURED, not absent.** Building with the pool
//: variables empty makes `isAuthConfigured` false, and the app then renders
//: "Auth is not configured — set VITE_COGNITO_USER_POOL_ID..." rather than the
//: login form. A first attempt asserted "no sign-in button is visible" against
//: that screen and passed, which is the shape of a test that proves nothing.
//:
//: Configured with these, Amplify reads the token store below and returns the
//: id token without a network call while it is unexpired. It never learns the
//: pool is fictional.
export const POOL_ID = "us-east-1_e2etestpool";
export const CLIENT_ID = "e2eclientid0000000000000";
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
    // Far enough out that a refresh is never attempted mid-run. Amplify only
    // reaches the network when it thinks the token has expired.
    exp: now + 60 * 60 * 24,
  });
  return `${header}.${payload}.e2e-not-a-real-signature`;
}

/**
 * Write the session before any application script runs.
 *
 * `addInitScript` runs on every navigation in the context, which matters: a
 * reload must find the session too, or half these specs would test the login
 * form by accident.
 */
export async function signIn(page: Page, library: string): Promise<void> {
  const token = fakeIdToken();
  await page.addInitScript(
    ([clientId, user, idToken, lib]) => {
      const at = `CognitoIdentityServiceProvider.${clientId}`;
      window.localStorage.setItem(`${at}.LastAuthUser`, user);
      window.localStorage.setItem(`${at}.${user}.idToken`, idToken);
      window.localStorage.setItem(`${at}.${user}.accessToken`, idToken);
      window.localStorage.setItem(`${at}.${user}.refreshToken`, "e2e-refresh");
      window.localStorage.setItem(`${at}.${user}.clockDrift`, "0");
      // `LibraryContext` mirrors the chosen library here, so a run starts where
      // a returning user would rather than on the switcher.
      window.localStorage.setItem("studio.library", lib);
    },
    [CLIENT_ID, EMAIL, token, library] as const,
  );
}
