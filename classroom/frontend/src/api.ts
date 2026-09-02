/**
 * The classroom API client.
 *
 * Two shapes of call live here and they differ in one important way: the
 * teacher's own pages are sent with an ID token, and the student reader is sent
 * with no credential at all. The reader must stay anonymous — a student
 * following a link has no account and never will.
 */

import { getIdToken, refreshTokens } from "./auth/oauth";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

export interface PageSummary {
  id: string;
  title: string;
  slug: string;
  published: boolean;
  created_at: string;
  updated_at: string;
  share_url: string | null;
}

export interface Page extends PageSummary {
  html: string;
}

export interface PublicPage {
  title: string;
  html: string;
  updated_at: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string };
    if (body.error) return body.error;
  } catch {
    /* non-JSON error body */
  }
  return `Request failed with HTTP ${response.status}.`;
}

async function authed<T>(path: string, init: RequestInit = {}): Promise<T> {
  const send = (token: string | null) =>
    fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: token } : {}),
        ...(init.headers ?? {}),
      },
    });

  let response = await send(getIdToken());

  // One retry, and only on 401: the token expired mid-session. Anything else
  // is a real failure and retrying it would just double the load.
  if (response.status === 401) {
    try {
      const refreshed = await refreshTokens();
      response = await send(refreshed.idToken);
    } catch {
      throw new ApiError("Your session has expired. Sign in again.", 401);
    }
  }

  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return (await response.json()) as T;
}

export async function listPages(): Promise<PageSummary[]> {
  const { pages } = await authed<{ pages: PageSummary[] }>("/pages");
  return pages;
}

export function getPage(id: string): Promise<Page> {
  return authed<Page>(`/pages/${id}`);
}

export function createPage(input: {
  title: string;
  html: string;
  published?: boolean;
}): Promise<Page> {
  return authed<Page>("/pages", { method: "POST", body: JSON.stringify(input) });
}

export function updatePage(
  id: string,
  input: Partial<{ title: string; html: string; published: boolean }>,
): Promise<Page> {
  return authed<Page>(`/pages/${id}`, { method: "PUT", body: JSON.stringify(input) });
}

export function deletePage(id: string): Promise<{ deleted: string }> {
  return authed<{ deleted: string }>(`/pages/${id}`, { method: "DELETE" });
}

/** The student reader. Deliberately unauthenticated — no token is attached. */
export async function readPublicPage(slug: string): Promise<PublicPage> {
  const response = await fetch(`${API_URL}/public/pages/${encodeURIComponent(slug)}`);
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return (await response.json()) as PublicPage;
}
