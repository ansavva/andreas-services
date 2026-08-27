/**
 * Authorization-code flow against Cognito Managed Login. The client is
 * confidential — the exchange happens here, in the www Lambda, and the secret
 * never reaches a browser.
 *
 * No refresh handling, by design: the exchange keeps only the ID token, which
 * the 8h session cookie then carries for its whole life. When it expires the
 * admin bounces back through hosted authorize.
 */
import { createHash, randomBytes } from "node:crypto";
import { createCookie } from "react-router";

import { env } from "./env.server";

/** Carries state + PKCE verifier + the post-login destination between the
 *  authorize redirect and the callback. Mirrors the session cookie's options;
 *  10 minutes is the whole round trip. */
const stateCookie = createCookie("__aswebsite_oauth", {
  httpOnly: true,
  sameSite: "lax",
  path: "/",
  secure: process.env.NODE_ENV === "production",
  secrets: [env.sessionSecret],
  maxAge: 600,
});

export type OAuthState = { state: string; verifier: string; next: string };

function base64url(buf: Buffer): string {
  return buf.toString("base64url");
}

export async function buildAuthorizeUrl({
  origin,
  next,
}: {
  origin: string;
  next: string;
}): Promise<{ url: string; cookieHeader: string }> {
  const state = base64url(randomBytes(32));
  // PKCE on a confidential client is redundant on paper — kept as defence in
  // depth against a leaked code, which costs nothing here.
  const verifier = base64url(randomBytes(32));
  const challenge = base64url(createHash("sha256").update(verifier).digest());

  const params = new URLSearchParams({
    client_id: env.cognitoClientId,
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: `${origin}/admin/callback`,
    state,
    code_challenge_method: "S256",
    code_challenge: challenge,
  });

  return {
    url: `https://${env.cognitoDomain}/oauth2/authorize?${params}`,
    cookieHeader: await stateCookie.serialize({ state, verifier, next }),
  };
}

export async function readStateCookie(request: Request): Promise<OAuthState | null> {
  const parsed = (await stateCookie.parse(request.headers.get("Cookie"))) as OAuthState | null;
  if (!parsed?.state || !parsed?.verifier) return null;
  return { state: parsed.state, verifier: parsed.verifier, next: parsed.next ?? "/admin" };
}

export function clearStateCookie(): Promise<string> {
  return stateCookie.serialize("", { maxAge: 0 });
}

export async function exchangeCode({
  code,
  verifier,
  redirectUri,
}: {
  code: string;
  verifier: string;
  redirectUri: string;
}): Promise<{ id_token: string }> {
  const credentials = Buffer.from(
    `${env.cognitoClientId}:${env.cognitoClientSecret}`,
  ).toString("base64");

  const res = await fetch(`https://${env.cognitoDomain}/oauth2/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${credentials}`,
    },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: env.cognitoClientId,
      code,
      redirect_uri: redirectUri,
      code_verifier: verifier,
    }),
  });

  if (!res.ok) {
    throw new Error(`Token exchange failed: ${res.status} ${await res.text()}`);
  }

  const body = (await res.json()) as { id_token?: string };
  if (!body.id_token) throw new Error("Token exchange returned no ID token");
  return { id_token: body.id_token };
}

/** Hosted sign-out. `logout_uri` must match a registered logout URL exactly. */
export function buildLogoutUrl(origin: string): string {
  const params = new URLSearchParams({
    client_id: env.cognitoClientId,
    logout_uri: `${origin}/admin/login`,
  });
  return `https://${env.cognitoDomain}/logout?${params}`;
}
