// Cognito auth, ported from the web app's `src/context/AuthContext.tsx`.
//
// Two things changed and nothing else did.
//
// 1. THE CONFIG SOURCE. The web app read the user-pool ids in a React Router
//    `loader`, so they arrived from the server on every request and could be
//    rotated without a rebuild. A static export has no server, so they are
//    build-time `EXPO_PUBLIC_*` values inlined by Metro. That also means
//    `Amplify.configure` can run once at module load rather than in an effect
//    waiting for props — which is what Amplify wants anyway, since a component
//    lower in the tree can call `signIn` before the provider's effect has fired.
//
// 2. THE STORAGE. `aws-amplify` on the web keeps its tokens in `localStorage`
//    and pulls entropy from `crypto.getRandomValues`. React Native has neither,
//    which is what `@aws-amplify/react-native`, `AsyncStorage`,
//    `react-native-get-random-values` and `react-native-url-polyfill` are for —
//    see `src/amplify.ts`, which must be imported before `aws-amplify` is.
import {
  confirmResetPassword,
  confirmSignUp,
  fetchAuthSession,
  getCurrentUser,
  resetPassword,
  signIn,
  signOut,
  signUp,
} from 'aws-amplify/auth';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { isAuthConfigured } from '../amplify';

interface AuthContextValue {
  authenticated: boolean;
  loading: boolean;
  email: string | null;
  login(email: string, password: string): Promise<void>;
  register(email: string, password: string): Promise<void>;
  confirm(email: string, code: string): Promise<void>;
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
    // With no user pool configured there is no session to restore and every call
    // below would throw. Settle into "signed out" rather than spinning forever —
    // the same guard the web app had.
    if (!isAuthConfigured) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthContextValue>(() => ({
    authenticated,
    loading,
    email,
    async login(username, password) {
      const result = await signIn({ username, password });
      if (!result.isSignedIn) throw new Error('Additional sign-in steps are required.');
      await refresh();
    },
    async register(username, password) {
      await signUp({ username, password, options: { userAttributes: { email: username } } });
    },
    async confirm(username, confirmationCode) {
      await confirmSignUp({ username, confirmationCode });
    },
    async beginReset(username) {
      await resetPassword({ username });
    },
    async finishReset(username, confirmationCode, newPassword) {
      await confirmResetPassword({ username, confirmationCode, newPassword });
    },
    async logout() {
      await signOut();
      await refresh();
    },
    async accessToken() {
      const session = await fetchAuthSession();
      const token = session.tokens?.accessToken?.toString();
      if (!token) throw new Error('Your session has expired. Please sign in again.');
      return token;
    },
  }), [authenticated, email, loading, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider.');
  return value;
}
