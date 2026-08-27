import { redirect } from "react-router";
import type { LoaderFunctionArgs, MetaFunction } from "react-router";

import { env } from "~/lib/env.server";
import { clearStateCookie, exchangeCode, readStateCookie } from "~/lib/oauth.server";
import { sessionCookieHeader, verifyIdToken } from "~/lib/session.server";

export const meta: MetaFunction = () => [
  { title: "Signing in · Andreas Services" },
  { name: "robots", content: "noindex" },
];

/** Bounce back to sign-in without leaking the reason into the URL. */
async function failed(reason: string, err?: unknown) {
  console.error("admin callback:", reason, err ?? "");
  return redirect("/admin/login", {
    headers: { "Set-Cookie": await clearStateCookie() },
  });
}

// No component: the loader always redirects.
export async function loader({ request }: LoaderFunctionArgs) {
  const params = new URL(request.url).searchParams;
  const stored = await readStateCookie(request);

  if (params.get("error")) return failed(params.get("error") ?? "unknown error");
  if (!stored) return failed("no state cookie");

  const code = params.get("code");
  if (!code) return failed("no authorization code");
  if (params.get("state") !== stored.state) return failed("state mismatch");

  let idToken: string;
  let email: string;
  try {
    const tokens = await exchangeCode({
      code,
      verifier: stored.verifier,
      redirectUri: `${env.publicOrigin}/admin/callback`,
    });
    idToken = tokens.id_token;
    // Verifies signature, issuer, expiry and `aud` against the client id.
    const claims = await verifyIdToken(idToken);
    email = typeof claims.email === "string" ? claims.email : "";
  } catch (err) {
    return failed("code exchange or token verification failed", err);
  }

  const next = stored.next.startsWith("/admin") ? stored.next : "/admin";

  // Two cookies in one response: commit the session, expire the state cookie.
  const headers = new Headers();
  headers.append("Set-Cookie", await sessionCookieHeader(idToken, email));
  headers.append("Set-Cookie", await clearStateCookie());
  return redirect(next, { headers });
}
