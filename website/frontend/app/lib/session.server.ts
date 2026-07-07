/**
 * Admin authentication: server-side Cognito login (USER_PASSWORD_AUTH) with the
 * resulting ID token stored in a signed, httpOnly session cookie. The token is
 * verified on every protected request and forwarded to the backend admin API.
 */
import {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
} from "@aws-sdk/client-cognito-identity-provider";
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

/** Authenticate against Cognito. Returns the ID token or throws with a
 *  user-safe message on invalid credentials. */
export async function login(email: string, password: string): Promise<{ idToken: string; email: string }> {
  const client = new CognitoIdentityProviderClient({ region: env.region });
  try {
    const out = await client.send(
      new InitiateAuthCommand({
        AuthFlow: "USER_PASSWORD_AUTH",
        ClientId: env.cognitoClientId,
        AuthParameters: { USERNAME: email, PASSWORD: password },
      }),
    );
    const idToken = out.AuthenticationResult?.IdToken;
    if (!idToken) {
      // e.g. a NEW_PASSWORD_REQUIRED challenge — not supported by this simple flow.
      throw new Error("Login could not be completed. Reset the admin password and try again.");
    }
    return { idToken, email };
  } catch (err) {
    const name = (err as { name?: string }).name;
    if (name === "NotAuthorizedException" || name === "UserNotFoundException") {
      throw new Error("Incorrect email or password.");
    }
    throw err;
  }
}

export async function createUserSession(idToken: string, email: string, redirectTo: string) {
  const session = await storage.getSession();
  session.set(SESSION_KEY, idToken);
  session.set(EMAIL_KEY, email);
  return redirect(redirectTo, {
    headers: { "Set-Cookie": await storage.commitSession(session) },
  });
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
