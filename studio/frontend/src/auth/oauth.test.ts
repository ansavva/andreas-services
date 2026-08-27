import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * PKCE has no server-side switch.
 *
 * Cognito will complete a code flow with no `code_challenge` at all — there is
 * no "require PKCE" setting on a user pool client to turn on — so nothing but
 * this file stops the challenge silently disappearing from the authorize URL.
 * Studio's client id ships in a static bundle, which is exactly the case PKCE
 * exists for: without it, an intercepted `?code=` is redeemable by anyone.
 */

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() {
      return map.size;
    },
  } as Storage;
}

// The module reads its config at import time, so the env has to be stubbed
// before the dynamic import below rather than in a top-level import.
async function loadModule() {
  vi.stubEnv("VITE_COGNITO_DOMAIN", "studio-auth.andreas.services");
  vi.stubEnv("VITE_COGNITO_CLIENT_ID", "test-client-id");
  vi.stubGlobal("sessionStorage", memoryStorage());
  vi.stubGlobal("localStorage", memoryStorage());
  vi.stubGlobal("window", { location: { origin: "http://localhost:5173" } });
  vi.resetModules();
  return import("./oauth");
}

async function s256(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  let binary = "";
  for (const byte of new Uint8Array(digest)) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

describe("buildAuthorizeUrl", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("carries a PKCE S256 challenge and a state parameter", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const params = new URL(await buildAuthorizeUrl()).searchParams;

    expect(params.get("code_challenge")).toBeTruthy();
    expect(params.get("code_challenge_method")).toBe("S256");
    expect(params.get("state")).toBeTruthy();
  });

  it("derives the challenge from the stored verifier, and does not send it", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const params = new URL(await buildAuthorizeUrl()).searchParams;
    const verifier = sessionStorage.getItem("studio.oauth.verifier");

    expect(verifier).toBeTruthy();
    // The verifier must never leave the browser on this leg — only its hash.
    // `plain` would satisfy the assertion above and defeat the whole point.
    expect(params.get("code_challenge")).not.toBe(verifier);
    expect(params.get("code_challenge")).toBe(await s256(verifier as string));
  });

  it("stashes the state it sends, so the callback can match it", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const params = new URL(await buildAuthorizeUrl()).searchParams;
    expect(sessionStorage.getItem("studio.oauth.state")).toBe(params.get("state"));
  });

  it("requests the code flow against the registered callback URI", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const url = new URL(await buildAuthorizeUrl("/c/char-0001"));

    expect(url.origin).toBe("https://studio-auth.andreas.services");
    expect(url.pathname).toBe("/oauth2/authorize");
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("client_id")).toBe("test-client-id");
    expect(url.searchParams.get("scope")).toBe("openid email profile");
    // Cognito matches this character for character against `callback_urls`.
    expect(url.searchParams.get("redirect_uri")).toBe("http://localhost:5173/auth/callback");
    expect(sessionStorage.getItem("studio.oauth.returnTo")).toBe("/c/char-0001");
  });

  it("generates a fresh verifier and state per call", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const first = new URL(await buildAuthorizeUrl()).searchParams;
    const second = new URL(await buildAuthorizeUrl()).searchParams;

    expect(first.get("code_challenge")).not.toBe(second.get("code_challenge"));
    expect(first.get("state")).not.toBe(second.get("state"));
  });
});

describe("handleCallback", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("refuses a code whose state this browser did not issue", async () => {
    const { buildAuthorizeUrl, handleCallback } = await loadModule();
    await buildAuthorizeUrl();

    await expect(
      handleCallback(new URLSearchParams({ code: "abc", state: "not-the-one-we-sent" })),
    ).rejects.toThrow(/state did not match/i);
  });

  it("sends the verifier — not the challenge — to the token endpoint", async () => {
    const { buildAuthorizeUrl, handleCallback, getIdToken } = await loadModule();

    const params = new URL(await buildAuthorizeUrl()).searchParams;
    const verifier = sessionStorage.getItem("studio.oauth.verifier");

    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id_token: "id.token.value",
        access_token: "access.token.value",
        refresh_token: "refresh.token.value",
        expires_in: 28800,
      }),
    });
    vi.stubGlobal("fetch", fetcher);

    await handleCallback(
      new URLSearchParams({ code: "abc", state: params.get("state") as string }),
    );

    const init = fetcher.mock.calls[0]?.[1] as { body: string };
    const body = new URLSearchParams(init.body);
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("code_verifier")).toBe(verifier);
    expect(body.get("redirect_uri")).toBe("http://localhost:5173/auth/callback");
    // The ID token is what the API Gateway authorizer validates — see
    // `apis/client.ts`. Storing the access token here 401s every call.
    expect(getIdToken()).toBe("id.token.value");
  });
});
