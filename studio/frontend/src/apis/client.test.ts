import { afterEach, describe, expect, it, vi } from "vitest";

// No user pool in a test, and none needed: what is under test is the header the
// client puts on a request, not the token. `isAuthConfigured` false is also the
// bare-checkout state, so this exercises the path a developer runs locally.
vi.mock("../auth/oauth", () => ({
  isAuthConfigured: () => false,
  getIdToken: () => null,
  refreshTokens: () => Promise.reject(new Error("not signed in")),
}));

import { ApiError, apiGet, setLibrary } from "./client";

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

describe("a structured failure", () => {
  // `support.structured` answers `{error: <code>, message: <sentence>, …extra}`.
  // Reading `error` first put the code on screen where the sentence belonged,
  // and dropped the extras a caller needs — the index `over_cap` would have had
  // to truncate, the digest `stale_digest` says is current now.
  function stubFailure(body: unknown, status = 409) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status, statusText: "Conflict", json: async () => body }),
    );
  }

  /** The `ApiError` a call threw — typed, so a test reads `.code` without a cast. */
  async function failureOf(call: Promise<unknown>): Promise<ApiError> {
    try {
      await call;
    } catch (error) {
      if (error instanceof ApiError) return error;
      throw error;
    }
    throw new Error("expected the call to fail");
  }

  it("shows the sentence and keeps the code beside it", async () => {
    stubFailure({ error: "over_cap", message: "18 references, and this model takes 7.", index: [1, 2] });

    const failure = await failureOf(apiGet("/api/characters/char-0001/selection"));

    expect(failure.message).toBe("18 references, and this model takes 7.");
    expect(failure.code).toBe("over_cap");
    expect(failure.body?.index).toEqual([1, 2]);
  });

  it("still reads an ordinary error, whose `error` IS the sentence", async () => {
    stubFailure({ error: "name is required" }, 400);

    const failure = await failureOf(apiGet("/api/runs"));

    expect(failure.message).toBe("name is required");
  });

  it("falls back to the status text when the body is not JSON", async () => {
    // An API Gateway authorizer rejection is not JSON. Throwing on the parse
    // would lose the status, which is the only thing that call carries.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        statusText: "Forbidden",
        json: async () => {
          throw new Error("not JSON");
        },
      }),
    );

    const failure = await failureOf(apiGet("/api/tree"));

    expect(failure.message).toBe("Forbidden");
    expect(failure.status).toBe(403);
  });
});
