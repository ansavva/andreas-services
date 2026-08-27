/**
 * OAuth 2.0 authorization-code flow with PKCE against Cognito Managed Login.
 *
 * Plain fetch, no SDK: the whole flow is four URLs and a token store, and the
 * Cognito and Amplify SDKs that wrap it each cost more bundle than this file.
 * Nothing here is scout-specific except the storage key prefix.
 */

const DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined;
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;

const VERIFIER_KEY = "scout.oauth.verifier";
const STATE_KEY = "scout.oauth.state";
const RETURN_TO_KEY = "scout.oauth.returnTo";
const TOKENS_KEY = "scout.auth.tokens";

export interface StoredTokens {
  idToken: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
}

/** Both build-time values must be present or no leg of the flow resolves. */
export function isConfigured(): boolean {
  return !!DOMAIN && !!CLIENT_ID;
}

function requireConfig(): { domain: string; clientId: string } {
  if (!DOMAIN || !CLIENT_ID) {
    throw new Error("Cognito is not configured.");
  }
  return { domain: DOMAIN, clientId: CLIENT_ID };
}

// The SPA is mounted under a basename (/app in prod), and Cognito matches
// redirect URIs character for character — so the callback URI must carry it.
// Derived exactly as App.tsx does, from the same env var.
function basename(): string {
  return ((import.meta.env.VITE_BASE as string | undefined) ?? "/app/").replace(/\/$/, "");
}

function redirectUri(): string {
  return `${window.location.origin}${basename()}/auth/callback`;
}

function logoutUri(): string {
  return `${window.location.origin}${basename()}`;
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
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64UrlEncode(new Uint8Array(digest));
}

// --- token store ---------------------------------------------------------

export function getTokens(): StoredTokens | null {
  const raw = localStorage.getItem(TOKENS_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredTokens;
  } catch {
    return null;
  }
}

function setTokens(tokens: StoredTokens): void {
  localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
}

export function clearTokens(): void {
  localStorage.removeItem(TOKENS_KEY);
}

export function getIdToken(): string | null {
  return getTokens()?.idToken ?? null;
}

export function isAuthenticated(): boolean {
  return !!getIdToken();
}

/** Email claim off the ID token, for the "signed in as" line. */
export function getUserEmail(): string | null {
  const idToken = getIdToken();
  if (!idToken) return null;
  const payload = idToken.split(".")[1];
  if (!payload) return null;
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const claims = JSON.parse(json) as { email?: string };
    return claims.email ?? null;
  } catch {
    return null;
  }
}

// --- authorize -----------------------------------------------------------

/**
 * Builds the hosted authorize URL and stashes what the callback needs to
 * finish: the PKCE verifier, the CSRF state, and where the user was headed.
 *
 * Cognito has no server-side "require PKCE" toggle, so the challenge below is
 * the only thing enforcing it — see oauth.test.ts.
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
export async function login(returnTo?: string): Promise<void> {
  window.location.assign(await buildAuthorizeUrl(returnTo));
}

// --- callback ------------------------------------------------------------

async function postToken(body: URLSearchParams): Promise<Record<string, string>> {
  const { domain } = requireConfig();
  const res = await fetch(`https://${domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    let detail = `token endpoint returned HTTP ${res.status}`;
    try {
      const err = (await res.json()) as { error?: string; error_description?: string };
      if (err.error) detail = err.error_description ?? err.error;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  return (await res.json()) as Record<string, string>;
}

/**
 * Exchanges the authorization code for tokens. Returns the path the user was
 * headed for before being bounced to the hosted page.
 */
export async function handleCallback(params: URLSearchParams): Promise<string> {
  const { clientId } = requireConfig();

  const error = params.get("error");
  if (error) {
    throw new Error(params.get("error_description") ?? error);
  }

  const code = params.get("code");
  if (!code) throw new Error("No authorization code in the callback.");

  // State is the CSRF guard: a code arriving without the state this browser
  // generated did not come from a sign-in this browser started.
  const expectedState = sessionStorage.getItem(STATE_KEY);
  if (!expectedState || params.get("state") !== expectedState) {
    throw new Error("Sign-in state did not match. Start again.");
  }

  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  if (!verifier) throw new Error("Sign-in verifier is missing. Start again.");

  const tokens = await postToken(
    new URLSearchParams({
      grant_type: "authorization_code",
      client_id: clientId,
      code,
      redirect_uri: redirectUri(),
      code_verifier: verifier,
    })
  );

  setTokens({
    idToken: tokens.id_token,
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresAt: Date.now() + Number(tokens.expires_in ?? 3600) * 1000,
  });

  const returnTo = sessionStorage.getItem(RETURN_TO_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(RETURN_TO_KEY);

  return returnTo || "/admin";
}

// --- refresh -------------------------------------------------------------

// Single-flight: refresh-token rotation retires the old token as it issues the
// new one, so two concurrent refreshes race to invalidate each other. Every
// caller awaits the same in-flight promise instead.
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
        })
      );

      const next: StoredTokens = {
        idToken: res.id_token,
        accessToken: res.access_token,
        // Rotation returns a NEW refresh token and retires the one just used.
        // Failing to persist it here would strand the session at the next
        // refresh — the response is the only place it is ever available.
        refreshToken: res.refresh_token ?? current.refreshToken,
        expiresAt: Date.now() + Number(res.expires_in ?? 3600) * 1000,
      };
      setTokens(next);
      return next;
    } catch (err) {
      clearTokens();
      throw err;
    } finally {
      inflight = null;
    }
  })();

  return inflight;
}

// --- logout --------------------------------------------------------------

/** Clears the local store and ends the hosted session too. */
export function logout(): void {
  const { domain, clientId } = requireConfig();
  clearTokens();
  const params = new URLSearchParams({
    client_id: clientId,
    logout_uri: logoutUri(),
  });
  window.location.assign(`https://${domain}/logout?${params.toString()}`);
}
