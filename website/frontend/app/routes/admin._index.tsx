import { Link, useSearchParams } from "react-router";
import type { LoaderFunctionArgs } from "react-router";

import { listSubmissions } from "~/lib/api.server";
import { requireAdmin } from "~/lib/session.server";

export async function loader({ request }: LoaderFunctionArgs) {
  const admin = await requireAdmin(request);
  const cursor = new URL(request.url).searchParams.get("cursor") ?? undefined;
  const { submissions, next_cursor } = await listSubmissions(admin.idToken, cursor);
  return { submissions, nextCursor: next_cursor };
}

export default function AdminDashboard({
  loaderData,
}: {
  loaderData: Awaited<ReturnType<typeof loader>>;
}) {
  const { submissions, nextCursor } = loaderData;
  const [params] = useSearchParams();

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h1 className="font-heading text-2xl font-semibold text-ink">Intake submissions</h1>
        <span className="text-sm text-muted">{submissions.length} shown</span>
      </div>

      {submissions.length === 0 ? (
        <p className="mt-10 text-muted">No submissions yet.</p>
      ) : (
        <ul className="mt-8 space-y-4">
          {submissions.map((s) => (
            <li key={s.id} className="rounded-lg border border-line bg-card p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-heading text-lg text-primary">{s.name || "—"}</span>{" "}
                  <a href={`mailto:${s.email}`} className="text-sm text-accent hover:underline">
                    {s.email}
                  </a>
                </div>
                <time className="text-xs text-muted" dateTime={s.created_at}>
                  {new Date(s.created_at).toLocaleString()}
                </time>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-muted">
                {s.company ? <span>Company: {s.company}</span> : null}
                {s.budget ? <span>Budget: {s.budget}</span> : null}
                {s.source_page ? <span>From: {s.source_page}</span> : null}
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm text-ink">{s.message}</p>
            </li>
          ))}
        </ul>
      )}

      {nextCursor ? (
        <div className="mt-8">
          <Link
            to={`/admin?cursor=${encodeURIComponent(nextCursor)}`}
            className="rounded-md border border-line px-4 py-2 text-sm font-medium text-ink hover:bg-surface-alt"
            preventScrollReset
          >
            Load older →
          </Link>
        </div>
      ) : params.get("cursor") ? (
        <p className="mt-8 text-sm text-muted">End of submissions.</p>
      ) : null}
    </div>
  );
}
