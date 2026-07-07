import type { ActionFunctionArgs } from "react-router";

import { postSubscribe } from "~/lib/api.server";

/** Resource route: newsletter signup → backend → Kit. */
export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData();
  const email = String(form.get("email") ?? "").trim();
  const firstName = String(form.get("first_name") ?? "").trim();

  try {
    await postSubscribe({ email, first_name: firstName || undefined });
    return { ok: true };
  } catch (err) {
    return { error: err instanceof Error ? err.message : "Something went wrong. Try again." };
  }
}
