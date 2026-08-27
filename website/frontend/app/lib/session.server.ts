/**
 * Admin session: the ID token obtained from the hosted code exchange
 * (`oauth.server.ts`), stored in a signed, httpOnly cookie. The token is
 * verified on every protected request and forwarded to the backend admin API.
 */
import { CognitoJwtVerifier } from "aws-jwt-verify";
import { createCookieSessionStorage, redirect } from "react-router";

import { env } from "./env.server";

const SESSION_KEY = "idToken";
const EMAIL_KEY = "email";

const storage = createCookieSessionStorage({
  cookie: {
    name: "__aswebsite_admin",
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: process.env.NODE_ENV === "production",
    secrets: [env.sessionSecret],
    maxAge: 60 * 60 * 8, // 8h
  },
});

let _verifier: ReturnType<typeof CognitoJwtVerifier.create> | null = null;
function verifier() {
  if (!_verifier) {
    _verifier = CognitoJwtVerifier.create({
      userPoolId: env.cognitoUserPoolId,
      tokenUse: "id",
      clientId: env.cognitoClientId,
    });
  }
  return _verifier;
}

/** Verify an ID token minted by the hosted flow. Throws when invalid. */
export async function verifyIdToken(idToken: string) {
  return verifier().verify(idToken);
}

/** `Set-Cookie` for a new admin session, for callers that must send other
 *  cookies in the same response. */
export async function sessionCookieHeader(idToken: string, email: string): Promise<string> {
  const session = await storage.getSession();
  session.set(SESSION_KEY, idToken);
  session.set(EMAIL_KEY, email);
  return storage.commitSession(session);
}

export async function logout(request: Request, redirectTo = "/admin/login") {
  const session = await storage.getSession(request.headers.get("Cookie"));
  return redirect(redirectTo, {
    headers: { "Set-Cookie": await storage.destroySession(session) },
  });
}

/** Return the verified admin identity, or null when unauthenticated/expired. */
export async function getAdmin(
  request: Request,
): Promise<{ idToken: string; email: string } | null> {
  const session = await storage.getSession(request.headers.get("Cookie"));
  const idToken = session.get(SESSION_KEY) as string | undefined;
  const email = (session.get(EMAIL_KEY) as string | undefined) ?? "";
  if (!idToken) return null;
  try {
    await verifier().verify(idToken);
    return { idToken, email };
  } catch {
    return null;
  }
}

/** Guard for protected admin routes. Redirects to login when unauthenticated. */
export async function requireAdmin(request: Request) {
  const admin = await getAdmin(request);
  if (!admin) {
    const url = new URL(request.url);
    throw redirect(`/admin/login?next=${encodeURIComponent(url.pathname)}`);
  }
  return admin;
}
