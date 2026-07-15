import { Amplify } from 'aws-amplify';
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

export interface AuthConfig {
  region: string;
  userPoolId: string;
  userPoolClientId: string;
}

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

export function AuthProvider({ children, config }: { children: ReactNode; config: AuthConfig }) {
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
    if (!config.userPoolId || !config.userPoolClientId) {
      setLoading(false);
      return;
    }
    Amplify.configure({
      Auth: {
        Cognito: {
          userPoolId: config.userPoolId,
          userPoolClientId: config.userPoolClientId,
          loginWith: { email: true },
          signUpVerificationMethod: 'code',
          userAttributes: { email: { required: true } },
        },
      },
    });
    void refresh();
  }, [config.userPoolClientId, config.userPoolId, refresh]);

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
