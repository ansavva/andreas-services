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
  published: boolean;
  /** How many files this lesson is made of. Zero until she uploads. */
  file_count: number;
  created_at: string;
  updated_at: string;
  share_url: string | null;
}

/** A page carries no HTML: its content is a directory of files in S3. */
export type Page = PageSummary;

export interface SignedUpload {
  path: string;
  key: string;
  url: string;
  content_type: string;
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

export function createPage(input: { title: string }): Promise<Page> {
  return authed<Page>("/pages", { method: "POST", body: JSON.stringify(input) });
}

export function updatePage(
  id: string,
  input: Partial<{ title: string; published: boolean }>,
): Promise<Page> {
  return authed<Page>(`/pages/${id}`, { method: "PUT", body: JSON.stringify(input) });
}

export function deletePage(id: string): Promise<{ deleted: string }> {
  return authed<{ deleted: string }>(`/pages/${id}`, { method: "DELETE" });
}

export async function listFiles(id: string): Promise<string[]> {
  const { files } = await authed<{ files: string[] }>(`/pages/${id}/files`);
  return files;
}

/**
 * Ask the API to sign a PUT for each file, then send the bytes STRAIGHT TO S3.
 *
 * The content never passes through our API: a zipped worksheet with its images
 * runs to tens of megabytes and API Gateway stops at 10MB, so routing it
 * through the Lambda would fail on exactly the lessons that matter most.
 */
export async function signUploads(
  id: string,
  paths: string[],
): Promise<SignedUpload[]> {
  const { uploads } = await authed<{ uploads: SignedUpload[] }>(
    `/pages/${id}/uploads`,
    { method: "POST", body: JSON.stringify({ paths }) },
  );
  return uploads;
}

/**
 * `Content-Type` must match what the API signed, exactly.
 *
 * A presigned URL signs that header, so sending a different one — or letting
 * the browser pick — fails with a signature error that reads like a bug in the
 * signing rather than a mismatch here.
 */
export async function putToS3(upload: SignedUpload, blob: Blob): Promise<void> {
  const response = await fetch(upload.url, {
    method: "PUT",
    headers: { "Content-Type": upload.content_type },
    body: blob,
  });
  if (!response.ok) {
    throw new ApiError(`Upload of ${upload.path} failed (HTTP ${response.status}).`, response.status);
  }
}

/** Tell the API the PUTs are done, so it can count what actually landed. */
export function completeUpload(id: string): Promise<Page & { files: string[] }> {
  return authed<Page & { files: string[] }>(`/pages/${id}/uploads/complete`, {
    method: "POST",
  });
}

