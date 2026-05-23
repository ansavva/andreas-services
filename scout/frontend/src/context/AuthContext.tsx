import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  type CognitoUserSession,
} from "amazon-cognito-identity-js";

const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID as string | undefined;
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined;

const userPool =
  USER_POOL_ID && CLIENT_ID
    ? new CognitoUserPool({ UserPoolId: USER_POOL_ID, ClientId: CLIENT_ID })
    : null;

interface AuthContextValue {
  user: string | null;
  idToken: string | null;
  loading: boolean;
  configured: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  idToken: null,
  loading: true,
  configured: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<string | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore an existing session from Cognito's localStorage on mount.
  useEffect(() => {
    if (!userPool) {
      setLoading(false);
      return;
    }
    const current = userPool.getCurrentUser();
    if (!current) {
      setLoading(false);
      return;
    }
    current.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (!err && session && session.isValid()) {
        setIdToken(session.getIdToken().getJwtToken());
        setUser(current.getUsername());
      }
      setLoading(false);
    });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    if (!userPool) {
      throw new Error("Cognito is not configured.");
    }
    const cognitoUser = new CognitoUser({ Username: email, Pool: userPool });
    const authDetails = new AuthenticationDetails({
      Username: email,
      Password: password,
    });

    await new Promise<void>((resolve, reject) => {
      cognitoUser.authenticateUser(authDetails, {
        onSuccess: (session) => {
          setIdToken(session.getIdToken().getJwtToken());
          setUser(cognitoUser.getUsername());
          resolve();
        },
        onFailure: (err: Error) => {
          reject(err);
        },
      });
    });
  }, []);

  const logout = useCallback(() => {
    if (userPool) {
      const current = userPool.getCurrentUser();
      current?.signOut();
    }
    setIdToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, idToken, loading, configured: !!userPool, login, logout }),
    [user, idToken, loading, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
