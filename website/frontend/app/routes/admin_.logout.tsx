import { redirect } from "react-router";
import type { ActionFunctionArgs } from "react-router";

import { env } from "~/lib/env.server";
import { buildLogoutUrl } from "~/lib/oauth.server";
import { logout } from "~/lib/session.server";

// Destroying the cookie is not enough: without the hosted /logout the Cognito
// session survives and the next sign-in skips the password prompt.
export async function action({ request }: ActionFunctionArgs) {
  return logout(request, buildLogoutUrl(env.publicOrigin));
}

export function loader() {
  return redirect("/admin/login");
}
