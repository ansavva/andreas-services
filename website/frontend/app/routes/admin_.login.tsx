import { Button } from "@ansavva/design-system";
import { Form, redirect, useActionData, useNavigation, useSearchParams } from "react-router";
import type { ActionFunctionArgs, LoaderFunctionArgs, MetaFunction } from "react-router";

import { createUserSession, getAdmin, login } from "~/lib/session.server";

export const meta: MetaFunction = () => [
  { title: "Admin login · Andreas Services" },
  { name: "robots", content: "noindex" },
];

export async function loader({ request }: LoaderFunctionArgs) {
  if (await getAdmin(request)) throw redirect("/admin");
  return null;
}

export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData();
  const email = String(form.get("email") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const next = String(form.get("next") ?? "/admin") || "/admin";

  if (!email || !password) {
    return { error: "Enter your email and password." };
  }
  try {
    const { idToken, email: verifiedEmail } = await login(email, password);
    return await createUserSession(idToken, verifiedEmail, next.startsWith("/admin") ? next : "/admin");
  } catch (err) {
    return { error: err instanceof Error ? err.message : "Login failed." };
  }
}

export default function AdminLogin() {
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const [params] = useSearchParams();
  const submitting = navigation.state !== "idle";

  const inputClass =
    "h-11 w-full rounded-md border border-line bg-card px-3 text-sm text-ink placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg";

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-6">
      <div className="w-full max-w-sm rounded-lg border border-line bg-card p-8">
        <h1 className="font-heading text-2xl font-semibold text-primary">Admin</h1>
        <p className="mt-1 text-sm text-muted">Sign in to view intake submissions.</p>

        <Form method="post" className="mt-6 flex flex-col gap-4">
          <input type="hidden" name="next" value={params.get("next") ?? "/admin"} />
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-ink">Email</span>
            <input type="email" name="email" required autoComplete="username" className={inputClass} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-ink">Password</span>
            <input
              type="password"
              name="password"
              required
              autoComplete="current-password"
              className={inputClass}
            />
          </label>

          {actionData?.error ? <p className="text-sm text-danger">{actionData.error}</p> : null}

          <Button type="submit" intent="primary" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </Form>
      </div>
    </div>
  );
}
