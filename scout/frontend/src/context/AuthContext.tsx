import { createContext, useCallback, useContext, useMemo, useState } from "react";
import * as oauth from "@/auth/oauth";

interface AuthContextValue {
  user: string | null;
  idToken: string | null;
  loading: boolean;
  configured: boolean;
  login: (returnTo?: string) => Promise<void>;
  logout: () => void;
  /** Re-reads the token store — the callback page calls this after exchange. */
  syncFromStore: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  idToken: null,
  loading: true,
  configured: false,
  login: async () => {},
  logout: () => {},
  syncFromStore: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // The token store is synchronous localStorage, so there is no session to
  // restore asynchronously and `loading` is only ever true for the first
  // render. It stays in the surface because ProtectedRoute keys off it.
  const [idToken, setIdToken] = useState<string | null>(() => oauth.getIdToken());
  const [user, setUser] = useState<string | null>(() => oauth.getUserEmail());

  const syncFromStore = useCallback(() => {
    setIdToken(oauth.getIdToken());
    setUser(oauth.getUserEmail());
  }, []);

  const login = useCallback(async (returnTo?: string) => {
    await oauth.login(returnTo);
  }, []);

  const logout = useCallback(() => {
    // Clears the local store and ends the hosted session, so the next visit
    // prompts for a password rather than silently re-authenticating.
    oauth.logout();
    setIdToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      idToken,
      loading: false,
      configured: oauth.isConfigured(),
      login,
      logout,
      syncFromStore,
    }),
    [user, idToken, login, logout, syncFromStore]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
