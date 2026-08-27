import { redirect } from "react-router";
import type { LoaderFunctionArgs, MetaFunction } from "react-router";

import { env } from "~/lib/env.server";
import { buildAuthorizeUrl } from "~/lib/oauth.server";
import { getAdmin } from "~/lib/session.server";

export const meta: MetaFunction = () => [
  { title: "Admin login · Andreas Services" },
  { name: "robots", content: "noindex" },
];

// No component: the loader always redirects, either to the dashboard or to the
// hosted sign-in pages, which own every credential screen.
export async function loader({ request }: LoaderFunctionArgs) {
  if (await getAdmin(request)) throw redirect("/admin");

  const url = new URL(request.url);
  const requested = url.searchParams.get("next") ?? "/admin";
  const next = requested.startsWith("/admin") ? requested : "/admin";

  const { url: authorizeUrl, cookieHeader } = await buildAuthorizeUrl({
    origin: env.publicOrigin,
    next,
  });
  return redirect(authorizeUrl, { headers: { "Set-Cookie": cookieHeader } });
}
