// Cognito auth over Managed Login's hosted pages.
//
// **The context implements no sign-in step, and that is the point.** Login,
// new-password, reset, TOTP enrolment and the challenge all happen on Cognito's
// hosted pages. What is here is the session: is there one, whose is it, how
// does a request get a token, and how does it end.
//
// The pool is still admin-create-only, so there is still no sign-up path — the
// hosted page will not offer one.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  getIdToken as readIdToken,
  getUserEmail,
  isAuthConfigured,
  isAuthenticated,
  login as redirectToHostedSignIn,
  logout as redirectToHostedSignOut,
  refreshTokens,
} from "../auth/oauth";

interface AuthContextValue {
  authenticated: boolean;
  loading: boolean;
  email: string | null;
  /** Whether a pool and a managed-login host were configured at build time. */
  configured: boolean;
  /** Leaves for the hosted sign-in page; never resolves in a live browser. */
  login(returnTo?: string): Promise<void>;
  /** Clears the local session, then ends the hosted one. */
  logout(): Promise<void>;
  /** The token the API accepts — see the note in `apis/client.ts`. */
  idToken(): Promise<string>;
  /** Re-reads the token store. The callback page calls this once it lands. */
  refresh(): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState<string | null>(null);

  const configured = isAuthConfigured();

  // Synchronous, unlike the Amplify version this replaces: the session is a
  // localStorage entry rather than a network round trip, so there is nothing
  // to await and `loading` is true for one render rather than for a request.
  const refresh = useCallback(() => {
    setAuthenticated(isAuthenticated());
    setEmail(getUserEmail());
    setLoading(false);
  }, []);

  useEffect(() => {
    // With nothing configured there is no session to restore and every call
    // below would throw. Settle into "signed out" rather than spinning.
    if (!configured) {
      setLoading(false);
      return;
    }
    refresh();
  }, [configured, refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({
      authenticated,
      loading,
      email,
      configured,
      refresh,

      login: redirectToHostedSignIn,

      // Async to keep the shape callers already `await`, and because the
      // navigation it starts is the last thing this tab does.
      //
      // It deliberately does NOT clear `authenticated` first. Doing so re-runs
      // the gate's effect, which sends a signed-out visitor to the hosted
      // SIGN-IN page — racing, and beating, the trip to `/logout` this starts.
      // The tab is leaving; there is no state worth updating on the way out.
      async logout() {
        redirectToHostedSignOut();
      },

      // **Read fresh per request, not cached.** A long-idle tab picks up a
      // renewed token instead of sending a stale one, and the renewal below
      // is single-flighted, so a burst of mounting screens costs one call.
      async idToken() {
        const token = readIdToken();
        if (token) return token;
        const renewed = await refreshTokens();
        return renewed.idToken;
      },
    }),
    [authenticated, configured, email, loading, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
