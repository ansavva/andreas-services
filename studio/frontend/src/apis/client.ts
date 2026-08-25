import { fetchAuthSession } from "aws-amplify/auth";

import { isAuthConfigured } from "../amplify";

const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/**
 * Which library every request is about, as `X-Studio-Library`.
 *
 * **A module variable set once, not an argument threaded through twenty call
 * sites.** The header has to be on *every* call — the API resolves a library
 * before any route runs, and a caller in more than one gets a 400 asking them to
 * name one — so the failure mode of threading it is that the one call site
 * somebody forgets is the one that writes into the wrong library. There is one
 * writer, `context/LibraryContext`, and this is the only reader.
 *
 * `null` until the library list has landed, and that is the ordinary state for
 * exactly one request: `GET /api/libraries` itself, which is answered without a
 * library on purpose. Nothing else is fetched before it resolves — see the gate
 * in `App`.
 */
let currentLibrary: string | null = null;

export function setLibrary(id: string | null): void {
  currentLibrary = id;
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
 * `DELETE /api/nodes` carries a JSON body, which is unusual but well-defined:
 * the alternative for a grid selection is a few hundred repeated `?ids=`
 * parameters, which is a URL length limit waiting to be hit on exactly the case
 * bulk delete exists for.
 *
 * **Every method here has to be in API Gateway's allowed-method list**, which
 * answers the browser's preflight instead of Flask — a method missing from it
 * fails as a network error with no status, which reads as the API being down.
 * **`PUT` is not on that list, and this file used to say it was.** Six entity
 * routes replace a whole collection — the profile, the reference bulk write, the
 * default set, a project's character links, a scene's shots, a movie's scenes —
 * and `docs/ENTITY_MODEL.md` spells every one of them `PUT`. The service does
 * not: adding a verb means changing the CORS list, the MOCK integration response
 * and two gateway responses together, so all six are `PATCH`, and replace is
 * told from merge by which key the body carries rather than by the verb. See
 * `app_factory.CORS_METHODS`.
 *
 * Four of those six were sent from here as `PUT` and died in the preflight —
 * a network error with no status, which is why they read as the API being down
 * rather than as a wrong verb. `PUT` is off the union below so the next one
 * fails to compile instead. A presigned upload still PUTs, and does not come
 * through here: see `apis/upload.ts`.
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
  // Sent whenever one is chosen, including for the single-library caller who
  // never sees a switcher: the API would resolve their sole membership without
  // it, and a header that is only present sometimes is a difference between two
  // callers that nothing else in the app would exercise.
  //
  // `X-Studio-Library` is a custom request header, so the browser preflights it
  // and API Gateway — not Flask — answers that preflight. It is in
  // `app_factory.CORS_HEADERS` and in `modules/api_gateway`'s `cors_headers`;
  // missing from either, this fails as a network error with no status.
  if (currentLibrary) headers["X-Studio-Library"] = currentLibrary;
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
