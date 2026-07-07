import type { ActionFunctionArgs } from "react-router";

import { postIntake } from "~/lib/api.server";

/** Resource route: intake ("scoped quote") submission → backend → DynamoDB. */
export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData();
  const payload = {
    name: String(form.get("name") ?? "").trim(),
    email: String(form.get("email") ?? "").trim(),
    company: String(form.get("company") ?? "").trim(),
    budget: String(form.get("budget") ?? "").trim(),
    message: String(form.get("message") ?? "").trim(),
    source_page: String(form.get("source_page") ?? "").trim(),
  };

  try {
    await postIntake(payload);
    return { ok: true };
  } catch (err) {
    return { error: err instanceof Error ? err.message : "Something went wrong. Try again." };
  }
}
