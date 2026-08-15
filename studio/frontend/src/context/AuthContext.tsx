// Cognito auth over Amplify's SRP flow.
//
// There is no register or confirm-signup path: the user pool is
// admin-create-only, so accounts arrive via `studio/scripts/create-user.sh` and
// the only flows a user can start are signing in, completing a forced first
// password change, and resetting a forgotten one.
import {
  confirmResetPassword,
  confirmSignIn,
  fetchAuthSession,
  getCurrentUser,
  resetPassword,
  signIn,
  signOut,
} from "aws-amplify/auth";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { isAuthConfigured } from "../amplify";

interface AuthContextValue {
  authenticated: boolean;
  loading: boolean;
  email: string | null;
  /** Set when Cognito wants a new password before the session is usable. */
  newPasswordRequired: boolean;
  login(email: string, password: string): Promise<void>;
  completeNewPassword(password: string): Promise<void>;
  beginReset(email: string): Promise<void>;
  finishReset(email: string, code: string, password: string): Promise<void>;
  logout(): Promise<void>;
  accessToken(): Promise<string>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState<string | null>(null);
  const [newPasswordRequired, setNewPasswordRequired] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const user = await getCurrentUser();
      setAuthenticated(true);
      setEmail(user.signInDetails?.loginId ?? user.username);
    } catch {
      setAuthenticated(false);
      setEmail(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // With no user pool configured there is no session to restore and every
    // call below would throw. Settle into "signed out" rather than spinning.
    if (!isAuthConfigured) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({
      authenticated,
      loading,
      email,
      newPasswordRequired,

      async login(username, password) {
        const result = await signIn({ username, password });
        if (
          !result.isSignedIn &&
          result.nextStep.signInStep === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED"
        ) {
          setNewPasswordRequired(true);
          return;
        }
        setNewPasswordRequired(false);
        await refresh();
      },

      async completeNewPassword(password) {
        await confirmSignIn({ challengeResponse: password });
        setNewPasswordRequired(false);
        await refresh();
      },

      async beginReset(username) {
        await resetPassword({ username });
      },

      async finishReset(username, confirmationCode, newPassword) {
        await confirmResetPassword({ username, confirmationCode, newPassword });
      },

      async logout() {
        await signOut();
        setAuthenticated(false);
        setEmail(null);
        setNewPasswordRequired(false);
      },

      async accessToken() {
        const session = await fetchAuthSession();
        const token = session.tokens?.accessToken?.toString();
        if (!token) throw new Error("Not signed in");
        return token;
      },
    }),
    [authenticated, email, loading, newPasswordRequired, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
