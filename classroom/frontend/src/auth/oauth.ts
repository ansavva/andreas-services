/**
 * OAuth 2.0 authorization-code flow with PKCE against Cognito Managed Login.
 *
 * Plain `fetch`, no SDK: the whole flow is three URLs and a token store. Sign-in,
 * password reset and forced first-password change all live on Cognito's hosted
 * page, which this service does not have to write, style or maintain.
 *
 * Services in this monorepo are self-contained and share no code, so this is
 * classroom's own copy of a flow studio and scout each keep their own version
 * of — with classroom's own storage keys, so two of these apps open in one
 * browser cannot read or clobber each other's session.
 */

const DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;

const VERIFIER_KEY = "classroom.oauth.verifier";
const STATE_KEY = "classroom.oauth.state";
const RETURN_TO_KEY = "classroom.oauth.returnTo";
const TOKENS_KEY = "classroom.auth.tokens";

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
    throw new Error("Cognito is not configured. See frontend/.env.local.example.");
  }
  return { domain: DOMAIN, clientId: CLIENT_ID };
}

function redirectUri(): string {
  return `${window.location.origin}${CALLBACK_PATH}`;
}

function logoutUri(): string {
  return `${window.location.origin}/`;
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
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
    // Private-mode Safari throws on `localStorage`, and a half-written value is
    // a parse error. Either way there is no session, which the app handles.
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
 * **The ID token.** The API Gateway authorizer validates an *identity* token;
 * the access token 401s on every call while sign-in itself looks healthy.
 */
export function getIdToken(): string | null {
  return getTokens()?.idToken ?? null;
}

export function isAuthenticated(): boolean {
  return getIdToken() !== null;
}

function claim(name: string): string | null {
  const payload = getIdToken()?.split(".")[1];
  if (!payload) return null;
  try {
    const claims = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as Record<string, string | undefined>;
    return claims[name] ?? null;
  } catch {
    return null;
  }
}

/** The email claim, for the header's "signed in as" line. */
export function getUserEmail(): string | null {
  return claim("email");
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

/**
 * Set the moment sign-out starts, and never cleared: the tab is leaving.
 *
 * Sign-out and sign-in are two `window.location.assign` calls racing to be
 * last, and sign-in is the one with an `await` in front of it. A sign-in
 * redirect started during sign-out would otherwise land after it, and Cognito's
 * session cookie is still set at that point — so sign-out silently does nothing.
 */
let signingOut = false;

export async function login(returnTo?: string): Promise<void> {
  const url = await buildAuthorizeUrl(returnTo);
  // Re-checked AFTER the await, not before: the gap is the whole problem.
  if (signingOut) return;
  window.location.assign(url);
}

// --- callback ------------------------------------------------------------

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
  // scopes produces; without this it would surface as a 401 on every later
  // call rather than here.
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
  if (!verifier) throw new Error("The sign-in verifier is missing. Start again.");

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
 * Single-flight. Every screen fetches on mount, so an expired token produces a
 * burst of simultaneous 401s and — without this — a burst of simultaneous
 * refreshes, each racing to write the store.
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
        // the one we have.
        refreshToken: res.refresh_token ?? current.refreshToken,
        expiresAt: Date.now() + (res.expires_in ?? 3600) * 1000,
      };
      setTokens(next);
      return next;
    } catch (err) {
      // A refresh that fails is a session that is over. Keeping it would retry
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
  const params = new URLSearchParams({ client_id: clientId, logout_uri: logoutUri() });
  window.location.assign(`https://${domain}/logout?${params.toString()}`);
}
