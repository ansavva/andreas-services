import { data } from "react-router";
import type { ActionFunctionArgs } from "react-router";

import { serializeTheme, type Theme } from "~/lib/theme.server";

/** Resource route: persist the light/dark preference in a cookie. */
export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData();
  const theme: Theme = form.get("theme") === "dark" ? "dark" : "light";
  return data({ theme }, { headers: { "Set-Cookie": await serializeTheme(theme) } });
}
