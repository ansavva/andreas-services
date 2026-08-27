import { afterEach, describe, expect, it, vi } from "vitest";

// No user pool in a test, and none needed: what is under test is the header the
// client puts on a request, not the token. `isAuthConfigured` false is also the
// bare-checkout state, so this exercises the path a developer runs locally.
vi.mock("../auth/oauth", () => ({
  isAuthConfigured: () => false,
  getIdToken: () => null,
  refreshTokens: () => Promise.reject(new Error("not signed in")),
}));

import { apiGet, setLibrary } from "./client";

function stubFetch() {
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

function headersOf(fetcher: ReturnType<typeof stubFetch>): Record<string, string> {
  return (fetcher.mock.calls[0]?.[1] as { headers: Record<string, string> }).headers;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setLibrary(null);
});

describe("the library header", () => {
  it("is sent on every request once a library is chosen", async () => {
    // The single-library caller sees no switcher and still sends this: the API
    // would resolve their sole membership without it, and a header that is only
    // present for some callers is a difference nothing else here exercises.
    const fetcher = stubFetch();
    setLibrary("lib-0001");

    await apiGet("/api/tree");

    expect(headersOf(fetcher)["X-Studio-Library"]).toBe("lib-0001");
  });

  it("is absent before one has been chosen", async () => {
    // Exactly one request is made in that state — `GET /api/libraries`, which
    // is answered without a library on purpose. Everything else waits for it.
    const fetcher = stubFetch();

    await apiGet("/api/libraries");

    expect(headersOf(fetcher)["X-Studio-Library"]).toBeUndefined();
  });

  it("follows the last library chosen rather than the first", async () => {
    const fetcher = stubFetch();
    setLibrary("lib-0001");
    setLibrary("lib-0002");

    await apiGet("/api/tree");

    expect(headersOf(fetcher)["X-Studio-Library"]).toBe("lib-0002");
  });
});
