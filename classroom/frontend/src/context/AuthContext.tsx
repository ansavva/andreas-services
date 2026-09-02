import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { getUserEmail, isAuthenticated, login, logout } from "../auth/oauth";

interface AuthValue {
  signedIn: boolean;
  email: string | null;
  signIn: (returnTo?: string) => void;
  signOut: () => void;
  /** Called by screens when a request comes back 401 and refresh failed. */
  sessionEnded: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(isAuthenticated);

  const sessionEnded = useCallback(() => setSignedIn(false), []);

  const value = useMemo<AuthValue>(
    () => ({
      signedIn,
      email: signedIn ? getUserEmail() : null,
      signIn: (returnTo?: string) => void login(returnTo),
      signOut: () => logout(),
      sessionEnded,
    }),
    [signedIn, sessionEnded],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside an AuthProvider");
  return value;
}
