/**
 * OAuth 2.0 authorization-code flow with PKCE against Cognito Managed Login.
 *
 * Plain `fetch`, no SDK. The whole flow is three URLs and a token store, which
 * is less code than configuring the SDK this replaced (`aws-amplify`) — and
 * the SDK's SRP path could not do the thing that matters here anyway, which is
 * hand sign-in to a hosted page studio does not have to write, style or
 * maintain. Password reset, forced first-password change and TOTP enrolment
 * all live on that page now; `components/auth/LoginForm.tsx` implemented three
 * of the four and is deleted.
 *
 * **This file is the browser's half only.** `studio login` — the CLI in
 * `pipeline/` — still authenticates with Cognito SRP through `InitiateAuth`
 * and renews with REFRESH_TOKEN_AUTH. Both flows stay enabled on the client
 * (`infra/modules/auth/main.tf`), and refresh-token rotation is deliberately
 * NOT enabled, because Cognito rejects it alongside the CLI's refresh flow.
 */

const DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;

const VERIFIER_KEY = "studio.oauth.verifier";
const STATE_KEY = "studio.oauth.state";
const RETURN_TO_KEY = "studio.oauth.returnTo";
const TOKENS_KEY = "studio.auth.tokens";

/**
 * The path Cognito redirects back to, registered character for character in
 * `callback_urls`. A constant rather than a literal in three places: the route
 * table, the authorize URL and the client's `callback_urls` must agree exactly,
 * and a mismatch fails at the redirect rather than at build or apply time.
 */
export const CALLBACK_PATH = "/auth/callback";

export interface StoredTokens {
  idToken: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
}

/** Both build-time values must be present or no leg of the flow resolves. */
export function isAuthConfigured(): boolean {
  return Boolean(DOMAIN && CLIENT_ID);
}

function requireConfig(): { domain: string; clientId: string } {
  if (!DOMAIN || !CLIENT_ID) {
    throw new Error(
      "Cognito is not configured. See frontend/.env.local.example.",
    );
  }
  return { domain: DOMAIN, clientId: CLIENT_ID };
}

function redirectUri(): string {
  return `${window.location.origin}${CALLBACK_PATH}`;
}

/** Where sign-out lands. Registered in the client's `logout_urls`. */
function logoutUri(): string {
  return `${window.location.origin}/`;
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function randomBase64Url(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

async function s256Challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  return base64UrlEncode(new Uint8Array(digest));
}

// --- the token store -----------------------------------------------------

export function getTokens(): StoredTokens | null {
  try {
    const raw = localStorage.getItem(TOKENS_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredTokens;
  } catch {
    // Private-mode Safari throws on `localStorage`, and a half-written value
    // is a parse error. Either way there is no session, which is a state the
    // app already handles.
    return null;
  }
}

function setTokens(tokens: StoredTokens): void {
  try {
    localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
  } catch {
    /* see `getTokens` */
  }
}

export function clearTokens(): void {
  try {
    localStorage.removeItem(TOKENS_KEY);
  } catch {
    /* see `getTokens` */
  }
}

/**
 * **The ID token, and the reason is in `apis/client.ts`.** The API Gateway
 * authorizer validates an *identity* token; the access token 401s on every
 * call while sign-in itself looks perfectly healthy.
 */
export function getIdToken(): string | null {
  return getTokens()?.idToken ?? null;
}

export function isAuthenticated(): boolean {
  return getIdToken() !== null;
}

/**
 * The `sub` claim off the ID token.
 *
 * Not decoration: a run's approval records WHO said yes as a Cognito sub, and a
 * sub is unreadable — "Approved by d4f85488-…" tells a person nothing about
 * whether it was them. Comparing it against this is what lets the run screen
 * say a name instead. It stays a comparison rather than a lookup because the
 * API resolves no directory, so the only identity the browser can name for
 * certain is the one holding the token.
 */
export function getUserSub(): string | null {
  const idToken = getIdToken();
  const payload = idToken?.split(".")[1];
  if (!payload) return null;
  try {
    const claims = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as { sub?: string };
    return claims.sub ?? null;
  } catch {
    return null;
  }
}

/** The email claim off the ID token, for the header's "signed in as" line. */
export function getUserEmail(): string | null {
  const idToken = getIdToken();
  const payload = idToken?.split(".")[1];
  if (!payload) return null;
  try {
    const claims = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as { email?: string };
    return claims.email ?? null;
  } catch {
    return null;
  }
}

// --- authorize -----------------------------------------------------------

/**
 * Builds the hosted authorize URL and stashes what the callback will need to
 * finish: the PKCE verifier, the CSRF state, and where the user was headed.
 *
 * **Cognito has no server-side "require PKCE" toggle.** It will complete a code
 * flow with no `code_challenge` at all, so the challenge below is the only
 * thing enforcing PKCE on a public client whose id ships in a static bundle —
 * and `oauth.test.ts` is the only thing stopping it disappearing from here.
 */
export async function buildAuthorizeUrl(returnTo?: string): Promise<string> {
  const { domain, clientId } = requireConfig();

  const verifier = randomBase64Url(32);
  const state = randomBase64Url(16);
  const challenge = await s256Challenge(verifier);

  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  if (returnTo) sessionStorage.setItem(RETURN_TO_KEY, returnTo);

  const params = new URLSearchParams({
    client_id: clientId,
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: redirectUri(),
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });

  return `https://${domain}/oauth2/authorize?${params.toString()}`;
}

/** Sends the browser to the hosted sign-in page. */
/**
 * Set the moment sign-out starts, and never cleared: the tab is leaving.
 *
 * Sign-out and sign-in are two `window.location.assign` calls racing to be
 * last, and sign-in is the one with an `await` in front of it — building the
 * authorize URL hashes a PKCE verifier. So a sign-in redirect started before
 * or during sign-out lands AFTER it, replacing the trip to `/logout` with a
 * trip to `/oauth2/authorize`. Cognito's session cookie is still set at that
 * point, so it answers with a fresh code and the user is signed straight back
 * in — sign-out silently does nothing. That is the bug this flag closes.
 */
let signingOut = false;

export async function login(returnTo?: string): Promise<void> {
  const url = await buildAuthorizeUrl(returnTo);
  // Re-checked AFTER the await, not before: the gap is the whole problem.
  if (signingOut) return;
  window.location.assign(url);
}

// --- callback ------------------------------------------------------------

/**
 * What `/oauth2/token` answers with. `refresh_token` is present on the
 * authorization-code exchange and absent from a non-rotating refresh response,
 * which is why it is optional here and defaulted at the call site.
 */
interface TokenResponse {
  id_token: string;
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
}

async function postToken(body: URLSearchParams): Promise<TokenResponse> {
  const { domain } = requireConfig();
  const response = await fetch(`https://${domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!response.ok) {
    let detail = `The token endpoint returned HTTP ${response.status}.`;
    try {
      const err = (await response.json()) as {
        error?: string;
        error_description?: string;
      };
      if (err.error) detail = err.error_description ?? err.error;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }

  const payload = (await response.json()) as Partial<TokenResponse>;
  // A 200 with no `id_token` is the shape a client configured for the wrong
  // scopes produces: the API authorizer takes an identity token, so a response
  // without one is a failure that would otherwise surface as a 401 on every
  // later call rather than here.
  if (!payload.id_token || !payload.access_token) {
    throw new Error("The token endpoint returned no ID token.");
  }
  return payload as TokenResponse;
}

/**
 * Exchanges the authorization code for tokens, and returns the path the user
 * was headed for before being bounced to the hosted page.
 */
export async function handleCallback(params: URLSearchParams): Promise<string> {
  const { clientId } = requireConfig();

  const error = params.get("error");
  if (error) throw new Error(params.get("error_description") ?? error);

  const code = params.get("code");
  if (!code) throw new Error("No authorization code in the callback.");

  // State is the CSRF guard: a code arriving without the state this browser
  // generated did not come from a sign-in this browser started.
  const expectedState = sessionStorage.getItem(STATE_KEY);
  if (!expectedState || params.get("state") !== expectedState) {
    throw new Error("Sign-in state did not match. Start again.");
  }

  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  if (!verifier)
    throw new Error("The sign-in verifier is missing. Start again.");

  const tokens = await postToken(
    new URLSearchParams({
      grant_type: "authorization_code",
      client_id: clientId,
      code,
      // Must match the authorize leg exactly, or Cognito rejects the exchange.
      redirect_uri: redirectUri(),
      code_verifier: verifier,
    }),
  );

  setTokens({
    idToken: tokens.id_token,
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token ?? "",
    expiresAt: Date.now() + (tokens.expires_in ?? 3600) * 1000,
  });

  const returnTo = sessionStorage.getItem(RETURN_TO_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(RETURN_TO_KEY);

  // Never back to the callback itself: that would re-run the exchange with a
  // code Cognito has already spent.
  return returnTo && returnTo !== CALLBACK_PATH ? returnTo : "/";
}

// --- refresh -------------------------------------------------------------

/**
 * Single-flight. Every screen in the app fetches on mount, so an expired token
 * produces a burst of simultaneous 401s and — without this — a burst of
 * simultaneous refreshes, each racing to write the store. One in-flight
 * promise, awaited by all of them.
 *
 * Studio's client has no refresh-token rotation, so a race here is merely
 * wasteful rather than fatal; scout's does, and there it would invalidate the
 * token mid-flight. Same shape either way, on purpose.
 */
let inflight: Promise<StoredTokens> | null = null;

export function refreshTokens(): Promise<StoredTokens> {
  if (inflight) return inflight;

  inflight = (async () => {
    const { clientId } = requireConfig();
    const current = getTokens();
    if (!current?.refreshToken) throw new Error("No refresh token.");

    try {
      const res = await postToken(
        new URLSearchParams({
          grant_type: "refresh_token",
          client_id: clientId,
          refresh_token: current.refreshToken,
        }),
      );

      const next: StoredTokens = {
        idToken: res.id_token,
        accessToken: res.access_token,
        // Cognito omits `refresh_token` from a non-rotating response, so keep
        // the one we have. Written from the response when it is there, which
        // is the only place a rotated token is ever available.
        refreshToken: res.refresh_token ?? current.refreshToken,
        expiresAt: Date.now() + (res.expires_in ?? 3600) * 1000,
      };
      setTokens(next);
      return next;
    } catch (err) {
      // A refresh that fails is a session that is over — a revoked token after
      // sign-out elsewhere, or one past its 30 days. Keeping it would retry
      // forever on every request.
      clearTokens();
      throw err;
    } finally {
      inflight = null;
    }
  })();

  return inflight;
}

// --- logout --------------------------------------------------------------

/**
 * Clears the local store and ends the hosted session too.
 *
 * Both halves matter. Dropping the tokens alone leaves the Cognito session
 * cookie on the managed-login domain, so the next visit signs straight back in
 * without a prompt — which reads as sign-out being broken.
 */
export function logout(): void {
  const { domain, clientId } = requireConfig();
  signingOut = true;
  clearTokens();
  const params = new URLSearchParams({
    client_id: clientId,
    logout_uri: logoutUri(),
  });
  window.location.assign(`https://${domain}/logout?${params.toString()}`);
}
