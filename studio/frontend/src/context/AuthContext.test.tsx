import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const store = { token: "id.token" as string | null };

vi.mock("../auth/oauth", () => ({
  SESSION_ENDED_EVENT: "studio:session-ended",
  isAuthConfigured: () => true,
  isAuthenticated: () => store.token !== null,
  getIdToken: () => store.token,
  getUserEmail: () => (store.token ? "person@example.com" : null),
  login: vi.fn(),
  logout: vi.fn(),
  refreshTokens: vi.fn(),
}));

import { AuthProvider, useAuth } from "./AuthContext";

function Probe() {
  const { authenticated, loading } = useAuth();
  return <span data-testid="auth">{loading ? "loading" : authenticated ? "in" : "out"}</span>;
}

afterEach(() => {
  cleanup();
  store.token = "id.token";
});

/**
 * The store is read once, at mount. A refresh that fails mid-page empties it
 * and says so on `window`; this is what turns that into `authenticated:
 * false`, so the gate sends the tab to sign in rather than leaving it on an
 * error it cannot recover from.
 */
it("drops authenticated when the session ends under it", () => {
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  expect(screen.getByTestId("auth").textContent).toBe("in");

  store.token = null;
  act(() => {
    window.dispatchEvent(new Event("studio:session-ended"));
  });
  expect(screen.getByTestId("auth").textContent).toBe("out");
});
