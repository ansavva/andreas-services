import { fetchAuthSession } from "aws-amplify/auth";

import { isAuthConfigured } from "../amplify";

const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Authenticated GET against the studio API.
 *
 * **The ID token, not the access token.** A REST API `COGNITO_USER_POOLS`
 * authorizer with no `authorization_scopes` on the method authorizes against an
 * *identity* token; hand it a Cognito access token — which carries `client_id`
 * and `token_use: "access"` rather than the `aud`/`token_use: "id"` the
 * authorizer checks — and every call 401s while sign-in itself looks perfectly
 * healthy. Same choice `website` and `scout` make against the same authorizer.
 *
 * The token is fetched per request rather than cached: Amplify already caches
 * and refreshes it internally, and reading it fresh means a long-idle tab picks
 * up a rotated token instead of sending a stale one.
 */
export async function apiGet<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  return request<T>("GET", path, { params });
}

/**
 * A write against the studio API.
 *
 * Split from `apiGet` only by what it sends — same token, same error shape.
 * `DELETE /api/objects` carries a JSON body, which is unusual but well-defined:
 * the alternative for a grid selection is a few hundred repeated `?key=`
 * parameters, which is a URL length limit waiting to be hit on exactly the case
 * bulk delete exists for.
 */
export async function apiSend<T>(
  method: "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  return request<T>(method, path, { body });
}

async function request<T>(
  method: string,
  path: string,
  options: { params?: Record<string, string | undefined>; body?: unknown },
): Promise<T> {
  const url = new URL(`${API_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, value);
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (isAuthConfigured) {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url.toString(), {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    // The API's own errors are JSON; API Gateway's authorizer rejections are
    // not, so fall back to the status text rather than throwing on the parse.
    let message = response.statusText;
    try {
      const body = (await response.json()) as { error?: string; message?: string };
      message = body.error ?? body.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}
