import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * PKCE has no server-side switch: Cognito will happily complete a code flow
 * with no `code_challenge` at all, so nothing but this test stops the
 * challenge from silently disappearing from the authorize URL.
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
  vi.stubEnv("VITE_COGNITO_DOMAIN", "scout-auth.andreas.services");
  vi.stubEnv("VITE_COGNITO_CLIENT_ID", "test-client-id");
  vi.stubEnv("VITE_BASE", "/app/");
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

    const url = new URL(await buildAuthorizeUrl());
    const params = url.searchParams;

    expect(params.get("code_challenge")).toBeTruthy();
    expect(params.get("code_challenge_method")).toBe("S256");
    expect(params.get("state")).toBeTruthy();
  });

  it("derives the challenge from the stored verifier, and does not send it", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const params = new URL(await buildAuthorizeUrl()).searchParams;
    const verifier = sessionStorage.getItem("scout.oauth.verifier");

    expect(verifier).toBeTruthy();
    // The verifier must never leave the browser on this leg — only its hash.
    expect(params.get("code_challenge")).not.toBe(verifier);
    expect(params.get("code_challenge")).toBe(await s256(verifier as string));
  });

  it("stashes the state it sends, so the callback can match it", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const params = new URL(await buildAuthorizeUrl()).searchParams;
    expect(sessionStorage.getItem("scout.oauth.state")).toBe(params.get("state"));
  });

  it("requests the code flow against the registered callback URI", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const url = new URL(await buildAuthorizeUrl("/admin/review-queue"));

    expect(url.origin).toBe("https://scout-auth.andreas.services");
    expect(url.pathname).toBe("/oauth2/authorize");
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("client_id")).toBe("test-client-id");
    expect(url.searchParams.get("scope")).toBe("openid email profile");
    // Cognito matches this character for character, basename included.
    expect(url.searchParams.get("redirect_uri")).toBe(
      "http://localhost:5173/app/auth/callback"
    );
    expect(sessionStorage.getItem("scout.oauth.returnTo")).toBe("/admin/review-queue");
  });

  it("generates a fresh verifier and state per call", async () => {
    const { buildAuthorizeUrl } = await loadModule();

    const first = new URL(await buildAuthorizeUrl()).searchParams;
    const second = new URL(await buildAuthorizeUrl()).searchParams;

    expect(first.get("code_challenge")).not.toBe(second.get("code_challenge"));
    expect(first.get("state")).not.toBe(second.get("state"));
  });
});
