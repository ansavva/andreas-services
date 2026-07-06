import { Form, Link, Outlet } from "react-router";
import type { LoaderFunctionArgs, MetaFunction } from "react-router";

import { requireAdmin } from "~/lib/session.server";

export const meta: MetaFunction = () => [
  { title: "Admin · Andreas Services" },
  { name: "robots", content: "noindex" },
];

export async function loader({ request }: LoaderFunctionArgs) {
  const admin = await requireAdmin(request);
  return { email: admin.email };
}

export default function AdminLayout({ loaderData }: { loaderData: { email: string } }) {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="border-b border-line bg-surface-alt/50">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <Link to="/admin" className="font-heading text-lg font-semibold text-primary">
            Admin
          </Link>
          <div className="flex items-center gap-4 text-sm text-muted">
            <span className="hidden sm:inline">{loaderData.email}</span>
            <Form method="post" action="/admin/logout">
              <button type="submit" className="font-medium text-ink hover:text-primary">
                Log out
              </button>
            </Form>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
        <Outlet />
      </main>
    </div>
  );
}
