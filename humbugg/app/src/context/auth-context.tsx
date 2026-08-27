// The session, held over Cognito Managed Login.
//
// The exported surface is what it was under Amplify minus the four flows the
// hosted pages now own — register, confirm, beginReset, finishReset all live on
// Cognito's side of the redirect, and `login()` no longer takes credentials
// because this app never sees them.
//
// `accessToken()` still returns the ACCESS token: the API validates access
// tokens and their `token_use` (`humbugg/backend/Humbugg.Api/Program.cs`), and
// the code flow issues the very same token the SRP flow did.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Platform } from 'react-native';

import {
  currentAccessToken,
  emailFromIdToken,
  isAuthConfigured,
  loadTokens,
  signInNative,
  signOut,
  startWebSignIn,
  type StoredTokens,
} from '../auth/oauth';

interface AuthContextValue {
  authenticated: boolean;
  loading: boolean;
  email: string | null;
  /** Launches the hosted flow. On web this navigates away and never returns. */
  login(returnTo?: string): Promise<void>;
  logout(): Promise<void>;
  accessToken(): Promise<string>;
  /** Adopts the tokens the `/auth/callback` route just exchanged; `null` signs out. */
  adopt(tokens: StoredTokens | null): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState<string | null>(null);

  const adopt = useCallback((tokens: StoredTokens | null) => {
    setAuthenticated(Boolean(tokens));
    setEmail(tokens ? emailFromIdToken(tokens.idToken) : null);
    setLoading(false);
  }, []);

  useEffect(() => {
    // With nothing configured there is no session to restore and every call
    // below can only fail. Settle into "signed out" rather than spinning.
    if (!isAuthConfigured) {
      setLoading(false);
      return;
    }
    void loadTokens().then(adopt).catch(() => adopt(null));
  }, [adopt]);

  const value = useMemo<AuthContextValue>(() => ({
    authenticated,
    loading,
    email,
    async login(returnTo) {
      if (Platform.OS === 'web') {
        // Navigates the whole document away; nothing after this runs.
        await startWebSignIn(returnTo);
        return;
      }
      adopt(await signInNative());
    },
    async logout() {
      adopt(null);
      await signOut();
    },
    accessToken: currentAccessToken,
    adopt,
  }), [adopt, authenticated, email, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider.');
  return value;
}
