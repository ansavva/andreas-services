/**
 * Thin server-side client for the Python backend API. The SSR loaders/actions
 * call this; the browser never talks to the backend directly.
 */
import { requireApiBase } from "./env.server";

export interface Submission {
  id: string;
  created_at: string;
  status: string;
  name?: string;
  email: string;
  company?: string;
  budget?: string;
  message: string;
  source_page?: string;
}

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: string };
    return body.error ?? `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

/** Submit an intake ("scoped quote") request. Throws with a user-safe message. */
export async function postIntake(payload: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${requireApiBase()}/intake`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
}

/** Add a newsletter subscriber via the backend (which talks to Kit). */
export async function postSubscribe(payload: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${requireApiBase()}/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
}

/** List intake submissions for the admin console. `idToken` is forwarded as a
 *  Bearer token; the API Gateway Cognito authorizer validates it. */
export async function listSubmissions(
  idToken: string,
  cursor?: string,
): Promise<{ submissions: Submission[]; next_cursor: string | null }> {
  const url = new URL(`${requireApiBase()}/admin/submissions`);
  if (cursor) url.searchParams.set("cursor", cursor);
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (res.status === 401 || res.status === 403) {
    throw new Response("Unauthorized", { status: 401 });
  }
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as { submissions: Submission[]; next_cursor: string | null };
}
