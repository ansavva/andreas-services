/**
 * Cognito has no server-side "require PKCE" toggle: it will complete a code
 * flow with no `code_challenge` at all. On a public client whose id ships in a
 * static bundle, the challenge built in `buildAuthorizeUrl` is the only thing
 * enforcing PKCE — and this suite is the only thing stopping it from silently
 * disappearing from the authorize URL.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.stubEnv("VITE_COGNITO_DOMAIN", "auth.example.test");
vi.stubEnv("VITE_COGNITO_CLIENT_ID", "test-client-id");

const { buildAuthorizeUrl, CALLBACK_PATH } = await import("./oauth");

describe("buildAuthorizeUrl", () => {
  beforeEach(() => sessionStorage.clear());

  it("sends an S256 code challenge", async () => {
    const url = new URL(await buildAuthorizeUrl());
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("keeps the verifier out of the URL and in session storage", async () => {
    const url = new URL(await buildAuthorizeUrl());
    const verifier = sessionStorage.getItem("classroom.oauth.verifier");
    expect(verifier).toBeTruthy();
    expect(url.toString()).not.toContain(verifier as string);
  });

  it("carries a CSRF state that matches what it stored", async () => {
    const url = new URL(await buildAuthorizeUrl());
    expect(url.searchParams.get("state")).toBe(
      sessionStorage.getItem("classroom.oauth.state"),
    );
  });

  it("asks for a code, against the registered callback path", async () => {
    const url = new URL(await buildAuthorizeUrl());
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("redirect_uri")).toBe(
      `${window.location.origin}${CALLBACK_PATH}`,
    );
  });

  it("remembers where the user was headed", async () => {
    await buildAuthorizeUrl("/pages/abc");
    expect(sessionStorage.getItem("classroom.oauth.returnTo")).toBe("/pages/abc");
  });
});
