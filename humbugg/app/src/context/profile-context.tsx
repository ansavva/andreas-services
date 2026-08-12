import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api, ApiError } from '../api/client';
import type { Profile } from '../types';
import { useAuth } from './auth-context';

interface ProfileContextValue {
  profile: Profile | null;
  loading: boolean;
  /** True once a fetch attempt has completed. `loaded && !profile` means the user still needs to set up a profile. */
  loaded: boolean;
  error: string | null;
  reload(): Promise<void>;
  setProfile(profile: Profile | null): void;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

/**
 * Loads the signed-in user's profile once and shares it across the app, so the avatar menu, settings
 * page, and dashboard all read and update a single source of truth. A missing profile (404) is a valid
 * state — a brand-new user who has not chosen a display name yet — represented as `profile === null`
 * after `loaded` becomes true.
 */
export function ProfileProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!auth.authenticated) return;
    setLoading(true);
    setError(null);
    try {
      const token = await auth.accessToken();
      setProfile(await api.getMe(token));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setProfile(null);
      else setError(err instanceof Error ? err.message : 'Unable to load your profile.');
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [auth]);

  useEffect(() => {
    if (auth.authenticated) {
      void reload();
    } else {
      setProfile(null);
      setLoaded(false);
      setError(null);
    }
  }, [auth.authenticated, reload]);

  const value = useMemo<ProfileContextValue>(
    () => ({ profile, loading, loaded, error, reload, setProfile }),
    [profile, loading, loaded, error, reload],
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile() {
  const value = useContext(ProfileContext);
  if (!value) throw new Error('useProfile must be used inside ProfileProvider.');
  return value;
}
