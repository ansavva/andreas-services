import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from 'react';
import { fetchProfile } from '../api/client';
import { Profile } from '../types';

interface AuthState {
  token: string | null;
  apiBaseUrl: string;
  cognitoDomain: string;
  clientId: string;
  clientSecret: string;
  profile: Profile | null;
}

interface LoginPayload {
  apiBaseUrl: string;
  cognitoDomain: string;
  clientId: string;
  clientSecret: string;
  username: string;
  password: string;
}

interface AuthContextValue extends AuthState {
  loading: boolean;
  error: string | null;
  loginWithPassword: (payload: LoginPayload) => Promise<void>;
  setTokenManually: (token: string, apiBaseUrl: string) => Promise<void>;
  logout: () => void;
}

const defaultApiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string) ?? 'http://localhost:5001';
const defaultCognitoDomain =
  (import.meta.env.VITE_COGNITO_DOMAIN as string) ?? 'https://your-domain.auth.us-east-1.amazoncognito.com';
const defaultClientId = (import.meta.env.VITE_COGNITO_CLIENT_ID as string) ?? 'humbugg-web';
const defaultClientSecret = (import.meta.env.VITE_COGNITO_CLIENT_SECRET as string) ?? 'replace-me';

const initialState: AuthState = {
  token: null,
  apiBaseUrl: defaultApiBaseUrl,
  cognitoDomain: defaultCognitoDomain,
  clientId: defaultClientId,
  clientSecret: defaultClientSecret,
  profile: null
};

const STORAGE_KEY = 'humbugg-web-auth';

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const saveState = (state: AuthState) => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      ...state,
      profile: state.profile ?? null
    })
  );
};

const loadState = (): AuthState => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return initialState;
    }
    const parsed = JSON.parse(raw);
    return {
      ...initialState,
      ...parsed,
      profile: parsed.profile ?? null
    };
  } catch {
    return initialState;
  }
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => loadState());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAndStoreProfile = useCallback(
    async (token: string | null, apiBaseUrl: string) => {
      if (!token) {
        setState((prev) => ({ ...prev, profile: null }));
        return;
      }
      try {
        const profile = await fetchProfile({ baseUrl: apiBaseUrl, token });
        setState((prev) => ({ ...prev, profile }));
      } catch (profileError) {
        console.error(profileError);
        setState((prev) => ({ ...prev, profile: null }));
      }
    },
    []
  );

  useEffect(() => {
    saveState(state);
  }, [state]);

  useEffect(() => {
    if (state.token && !state.profile) {
      fetchAndStoreProfile(state.token, state.apiBaseUrl);
    }
  }, [fetchAndStoreProfile, state.apiBaseUrl, state.profile, state.token]);

  const loginWithPassword = useCallback(
    async (payload: LoginPayload) => {
      setLoading(true);
      setError(null);
      try {
        const body = new URLSearchParams({
          grant_type: 'password',
          scope: 'openid profile email',
          username: payload.username,
          password: payload.password,
          client_id: payload.clientId
        });
        if (payload.clientSecret.trim()) {
          body.append('client_secret', payload.clientSecret);
        }

        const response = await fetch(`${payload.cognitoDomain.replace(/\/+$/, '')}/oauth2/token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body
        });

        const tokenPayload = await response.json();
        if (!response.ok) {
          throw new Error(tokenPayload.error_description || 'Unable to authenticate.');
        }

        const token = tokenPayload.access_token as string;
        const nextState: AuthState = {
          token,
          apiBaseUrl: payload.apiBaseUrl,
          cognitoDomain: payload.cognitoDomain,
          clientId: payload.clientId,
          clientSecret: payload.clientSecret,
          profile: null
        };
        setState(nextState);
        saveState(nextState);
        await fetchAndStoreProfile(token, payload.apiBaseUrl);
      } catch (authError) {
        if (authError instanceof Error) {
          setError(authError.message);
        } else {
          setError('Unable to authenticate.');
        }
        throw authError;
      } finally {
        setLoading(false);
      }
    },
    [fetchAndStoreProfile]
  );

  const setTokenManually = useCallback(
    async (token: string, apiBaseUrl: string) => {
      const nextState: AuthState = {
        ...state,
        token,
        apiBaseUrl,
        profile: null
      };
      setState(nextState);
      saveState(nextState);
      await fetchAndStoreProfile(token, apiBaseUrl);
    },
    [fetchAndStoreProfile, state]
  );

  const logout = useCallback(() => {
    setState(initialState);
    saveState(initialState);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      loading,
      error,
      loginWithPassword,
      setTokenManually,
      logout
    }),
    [error, loading, loginWithPassword, logout, setTokenManually, state]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
