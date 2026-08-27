// Hosted sign-in against Cognito Managed Login, on `expo-auth-session`.
//
// Amplify is gone from this app. Its `signInWithRedirect` needs the
// `@aws-amplify/rtn-web-browser` NATIVE module, and humbugg has no prebuild, no
// dev-client and no eas.json — so on the two runtimes this app actually has
// today, Expo Go and the web export, it cannot load. expo-auth-session runs in
// both unchanged and keeps working in a future EAS build.
//
// The whole flow is authorization code + PKCE (S256). PKCE is not optional
// here in a way Terraform could enforce: Cognito has no server-side "require
// PKCE" switch, so the only thing that keeps this client from degrading to a
// bare code flow is this file — which is why `oauth.test.ts` asserts the
// authorize URL rather than trusting the config.
//
// Full decision record: humbugg/docs/auth-managed-login.md.
import {
  AuthRequest,
  CodeChallengeMethod,
  ResponseType,
  TokenTypeHint,
  exchangeCodeAsync,
  makeRedirectUri,
  refreshAsync,
  revokeAsync,
  type TokenResponse,
} from 'expo-auth-session';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';

import { sessionKeys, sessionStore } from '../utils/session-store';

// Three separate static lookups: Metro substitutes `process.env.EXPO_PUBLIC_X`
// textually, so a computed key inlines as `undefined`.
const COGNITO_DOMAIN = process.env.EXPO_PUBLIC_COGNITO_DOMAIN ?? '';
const CLIENT_ID = process.env.EXPO_PUBLIC_COGNITO_CLIENT_ID ?? '';

/**
 * Whether a hosted flow was configured at build time. False in a bare checkout
 * with no `.env.local`; the auth context uses it to settle into "signed out"
 * rather than spinning on a session that can only fail.
 */
export const isAuthConfigured = Boolean(COGNITO_DOMAIN && CLIENT_ID);

/**
 * Managed Login's endpoints. Spelled out rather than fetched from
 * `/.well-known/openid-configuration`, because that fetch would be a network
 * round trip on every cold start to learn four constants.
 */
export const discovery = {
  authorizationEndpoint: `https://${COGNITO_DOMAIN}/oauth2/authorize`,
  tokenEndpoint: `https://${COGNITO_DOMAIN}/oauth2/token`,
  revocationEndpoint: `https://${COGNITO_DOMAIN}/oauth2/revoke`,
};

const SCOPES = ['openid', 'email', 'profile'];

/** Where the hosted `/logout` sends the browser back to, per platform. */
function logoutReturnUri(): string {
  return Platform.OS === 'web' ? `${globalThis.location.origin}/login` : 'humbugg://auth/logout';
}

/**
 * The redirect Cognito returns the authorization code to. Registered in
 * both env directories under `humbugg/infra/envs` as EXACT strings — Cognito does no prefix or
 * wildcard matching, so anything this returns that is not registered there
 * fails as `redirect_mismatch` on the hosted page, not in this app.
 */
export function redirectUri(): string {
  if (Platform.OS === 'web') return `${globalThis.location.origin}/auth/callback`;
  return makeRedirectUri({ scheme: 'humbugg', path: 'auth/callback' });
}

/**
 * The authorization request. Exported because the PKCE test builds one and
 * reads the URL it produces.
 */
export function createAuthRequest(uri: string = redirectUri()): AuthRequest {
  return new AuthRequest({
    clientId: CLIENT_ID,
    redirectUri: uri,
    scopes: SCOPES,
    responseType: ResponseType.Code,
    usePKCE: true,
    codeChallengeMethod: CodeChallengeMethod.S256,
  });
}

// ---------------------------------------------------------------------------
// Token store
// ---------------------------------------------------------------------------

export interface StoredTokens {
  accessToken: string;
  /** Absent only if Cognito ever stops issuing one; then the session simply ends at expiry. */
  refreshToken: string | null;
  idToken: string | null;
  /** Epoch milliseconds. */
  expiresAt: number;
}

// One key per token rather than a single JSON blob: iOS SecureStore warns above
// 2048 bytes per value, and three Cognito JWTs together clear that easily.
// SecureStore keys accept only alphanumerics, '.', '-' and '_'.
const KEYS = {
  access: 'humbugg.auth.accessToken',
  refresh: 'humbugg.auth.refreshToken',
  id: 'humbugg.auth.idToken',
  expiresAt: 'humbugg.auth.expiresAt',
} as const;

interface KeyStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

// localStorage, not sessionStorage: a signed-in tab that is closed and reopened
// should still be signed in, which is what the Amplify build did too. Every
// access is guarded because Safari throws on it in some privacy modes.
const webKeyStore: KeyStore = {
  async get(key) {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  },
  async set(key, value) {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      /* a browser that refuses storage gets a session that ends with the tab */
    }
  },
  async remove(key) {
    try {
      globalThis.localStorage?.removeItem(key);
    } catch {
      /* nothing to remove if nothing could be written */
    }
  },
};

const secureKeyStore: KeyStore = {
  get: (key) => SecureStore.getItemAsync(key),
  set: (key, value) => SecureStore.setItemAsync(key, value),
  remove: (key) => SecureStore.deleteItemAsync(key),
};

const keyStore: KeyStore = Platform.OS === 'web' ? webKeyStore : secureKeyStore;

export async function loadTokens(): Promise<StoredTokens | null> {
  const [accessToken, refreshToken, idToken, expiresAt] = await Promise.all([
    keyStore.get(KEYS.access),
    keyStore.get(KEYS.refresh),
    keyStore.get(KEYS.id),
    keyStore.get(KEYS.expiresAt),
  ]);
  if (!accessToken) return null;
  return {
    accessToken,
    refreshToken,
    idToken,
    expiresAt: Number(expiresAt ?? 0),
  };
}

/**
 * Persists a token response.
 *
 * **Refresh-token rotation is ENABLED on this client** (see
 * `humbugg/infra/modules/auth/main.tf`), so every refresh returns a NEW refresh
 * token and retires the one that bought it. Failing to write it back would leave
 * the app holding a dead token and sign the user out an hour later. Cognito
 * omits the field on a plain refresh only in the non-rotating case, so the
 * previous value is kept rather than cleared when it is absent.
 */
export async function saveTokens(response: TokenResponse): Promise<StoredTokens> {
  const existing = await loadTokens();
  const refreshToken = response.refreshToken ?? existing?.refreshToken ?? null;
  const idToken = response.idToken ?? existing?.idToken ?? null;
  const expiresAt = (response.issuedAt + (response.expiresIn ?? 3600)) * 1000;

  await Promise.all([
    keyStore.set(KEYS.access, response.accessToken),
    keyStore.set(KEYS.expiresAt, String(expiresAt)),
    refreshToken ? keyStore.set(KEYS.refresh, refreshToken) : keyStore.remove(KEYS.refresh),
    idToken ? keyStore.set(KEYS.id, idToken) : keyStore.remove(KEYS.id),
  ]);

  return { accessToken: response.accessToken, refreshToken, idToken, expiresAt };
}

export async function clearTokens(): Promise<void> {
  await Promise.all(Object.values(KEYS).map((key) => keyStore.remove(key)));
}

// ---------------------------------------------------------------------------
// Refresh
// ---------------------------------------------------------------------------

export class SessionExpiredError extends Error {
  constructor() {
    super('Your session has expired. Please sign in again.');
  }
}

// Single-flight. With rotation on, two concurrent refreshes would spend the same
// refresh token twice; the client's 30-second retry grace period absorbs a race
// this misses, but not spending it twice is cheaper than relying on the grace.
let refreshInFlight: Promise<StoredTokens> | null = null;

async function runRefresh(refreshToken: string): Promise<StoredTokens> {
  try {
    const response = await refreshAsync({ clientId: CLIENT_ID, refreshToken, scopes: SCOPES }, discovery);
    return await saveTokens(response);
  } catch {
    await clearTokens();
    throw new SessionExpiredError();
  } finally {
    refreshInFlight = null;
  }
}

/**
 * The ACCESS token, refreshed if it is about to expire.
 *
 * The API validates access tokens and their `token_use`
 * (`humbugg/backend/Humbugg.Api/Program.cs`), so this is what every request
 * carries — the code flow issues exactly the same token the SRP flow did, which
 * is why no backend change was needed.
 */
export async function currentAccessToken(): Promise<string> {
  const tokens = await loadTokens();
  if (!tokens) throw new SessionExpiredError();
  // A minute of headroom: a token that expires mid-flight fails the request.
  if (Date.now() < tokens.expiresAt - 60_000) return tokens.accessToken;
  if (!tokens.refreshToken) {
    await clearTokens();
    throw new SessionExpiredError();
  }
  refreshInFlight ??= runRefresh(tokens.refreshToken);
  return (await refreshInFlight).accessToken;
}

// ---------------------------------------------------------------------------
// Sign-in
// ---------------------------------------------------------------------------

/** Thrown when the user closes the hosted page without signing in. */
export class SignInCancelledError extends Error {
  constructor() {
    super('Sign-in was cancelled.');
  }
}

/**
 * Native sign-in: the hosted page opens in the system browser and
 * `promptAsync` resolves with the code, so the whole flow finishes here.
 *
 * In Expo Go on a device the `humbugg://` scheme belongs to Expo Go rather than
 * to this app, so this path needs a dev build to exercise for real. Day-to-day
 * verification is the web flow on :8081.
 */
export async function signInNative(): Promise<StoredTokens> {
  const uri = redirectUri();
  const request = createAuthRequest(uri);
  const result = await request.promptAsync(discovery);

  if (result.type === 'error') throw new Error(result.error?.message ?? 'Sign-in failed.');
  if (result.type !== 'success') throw new SignInCancelledError();

  const response = await exchangeCodeAsync(
    {
      clientId: CLIENT_ID,
      code: result.params.code,
      redirectUri: uri,
      extraParams: { code_verifier: request.codeVerifier ?? '' },
    },
    discovery,
  );
  return saveTokens(response);
}

/**
 * Web sign-in, part one: leave the app entirely.
 *
 * A popup would be the other option and is worse — it is what pop-up blockers
 * eat, and the export is a single-page app that can just come back to
 * `/auth/callback`. The verifier and state have to outlive the navigation, so
 * they go to sessionStorage, which is scoped to this tab and dies with it.
 */
export async function startWebSignIn(returnTo?: string): Promise<void> {
  const request = createAuthRequest(redirectUri());
  const url = await request.makeAuthUrlAsync(discovery);

  sessionStore.set(sessionKeys.oauthVerifier, request.codeVerifier ?? '');
  sessionStore.set(sessionKeys.oauthState, request.state);
  if (returnTo) sessionStore.set(sessionKeys.returnTo, returnTo);

  globalThis.location.assign(url);
}

/** Web sign-in, part two: the `/auth/callback` route hands the query back here. */
export async function completeWebSignIn(params: {
  code?: string;
  state?: string;
  error?: string;
  errorDescription?: string;
}): Promise<StoredTokens> {
  const verifier = sessionStore.get(sessionKeys.oauthVerifier);
  const expectedState = sessionStore.get(sessionKeys.oauthState);
  sessionStore.remove(sessionKeys.oauthVerifier);
  sessionStore.remove(sessionKeys.oauthState);

  if (params.error) throw new Error(params.errorDescription || params.error);
  if (!params.code) throw new Error('The sign-in response carried no authorization code.');
  // State is the CSRF check: a code that arrives without the state this tab
  // generated was not requested by this tab.
  if (!expectedState || params.state !== expectedState) {
    throw new Error('This sign-in response does not match the request from this browser.');
  }

  const response = await exchangeCodeAsync(
    {
      clientId: CLIENT_ID,
      code: params.code,
      redirectUri: redirectUri(),
      extraParams: { code_verifier: verifier ?? '' },
    },
    discovery,
  );
  return saveTokens(response);
}

// ---------------------------------------------------------------------------
// Sign-out
// ---------------------------------------------------------------------------

/**
 * Clears the local store, best-effort revokes the refresh token, then visits the
 * hosted `/logout` — without which Cognito's own session cookie survives and the
 * next sign-in silently signs the same person straight back in.
 */
export async function signOut(): Promise<void> {
  const tokens = await loadTokens();
  await clearTokens();

  if (tokens?.refreshToken) {
    try {
      await revokeAsync(
        { clientId: CLIENT_ID, token: tokens.refreshToken, tokenTypeHint: TokenTypeHint.RefreshToken },
        discovery,
      );
    } catch {
      /* the local store is already gone; a failed revoke must not block sign-out */
    }
  }

  const returnUri = logoutReturnUri();
  const url =
    `https://${COGNITO_DOMAIN}/logout` +
    `?client_id=${encodeURIComponent(CLIENT_ID)}` +
    `&logout_uri=${encodeURIComponent(returnUri)}`;

  if (Platform.OS === 'web') globalThis.location.assign(url);
  else await WebBrowser.openAuthSessionAsync(url, returnUri);
}

// ---------------------------------------------------------------------------
// Display identity
// ---------------------------------------------------------------------------

/**
 * The `email` claim of the ID token, for display only.
 *
 * **Deliberately unverified.** Nothing is authorized on it: every authorization
 * decision is the API's, made against the access token it verifies itself. This
 * only fills in a name in the account menu.
 */
export function emailFromIdToken(idToken: string | null): string | null {
  if (!idToken) return null;
  const payload = idToken.split('.')[1];
  if (!payload) return null;
  try {
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const claims = JSON.parse(globalThis.atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='))) as {
      email?: string;
    };
    return claims.email ?? null;
  } catch {
    return null;
  }
}
