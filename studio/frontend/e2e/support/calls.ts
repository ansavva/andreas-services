/**
 * Reading back what the app asked the API for — shared by every spec that
 * asserts on a SEQUENCE of calls rather than on what the screen shows.
 *
 * Lived in `runs.spec.ts` until the create bar needed the same log: Enter on
 * the bar has to make exactly `POST /api/runs` then `POST /api/runs/<id>/submit`,
 * which is the same kind of claim the armed-button specs make.
 */
import type { Page } from "@playwright/test";

/** One call the app made, as this file wants to read it back. */
export interface Call {
  method: string;
  /** Kept so a spec can prove the call was served by the stub, not by :8000. */
  origin: string;
  path: string;
  query: URLSearchParams;
  body: Record<string, unknown>;
}

/**
 * Every `/api` call, in the order the browser made them.
 *
 * Registered before the first navigation, because a listener attached
 * afterwards cannot have seen what it is about to assert on — the same mistake
 * an early version of `browse.spec.ts`'s escape check made.
 */
export function log(page: Page): Call[] {
  const calls: Call[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) return;
    let body: Record<string, unknown> = {};
    try {
      body = (request.postDataJSON() ?? {}) as Record<string, unknown>;
    } catch {
      /* a GET, or a write with no JSON body */
    }
    calls.push({
      method: request.method(),
      origin: url.origin,
      path: url.pathname,
      query: url.searchParams,
      body,
    });
  });
  return calls;
}

export const wrote = (calls: Call[]) => calls.filter((call) => call.method !== "GET");
export const spell = (calls: Call[]) =>
  calls.map((call) => `${call.method} ${call.path}`);

/**
 * Calls that went somewhere other than the page's own origin.
 *
 * **`npm run e2e` builds and previews on :4173 and must not depend on a dev
 * server.** A developer usually has `dev-up.sh` running while writing these, so
 * a spec that only passed because :8000 happened to be up would pass locally and
 * fail in CI — where there is no stack at all. This is that assumption made
 * checkable inside the flows that write.
 */
export function escaped(calls: Call[], page: Page): string[] {
  const here = new URL(page.url()).origin;
  return calls
    .filter((call) => call.origin !== here)
    .map((call) => `${call.origin}${call.path}`);
}
