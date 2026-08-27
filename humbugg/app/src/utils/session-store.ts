// `sessionStorage` carries the values that have to survive a navigation across
// an auth boundary: where to return after signing in, the PKCE verifier and CSRF
// state of an in-flight hosted sign-in, and a freshly-minted invite link that
// the API will never show again.
//
// There is no `sessionStorage` on a device. This is the one seam that hides that:
// the browser's own store on web (so a real page reload still survives, exactly
// as today), and a module-level map on native — which is the right lifetime
// there anyway, since "the session" is how long the app is running.
//
// Deliberately NOT AsyncStorage: every value here is short-lived and one of them
// is an invite secret. Persisting them to disk would outlive their purpose.
import { Platform } from 'react-native';

const memory = new Map<string, string>();

const webStorage = (): Storage | null => {
  if (Platform.OS !== 'web') return null;
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    // Safari throws on `sessionStorage` access in some privacy modes.
    return null;
  }
};

export const sessionStore = {
  get(key: string): string | null {
    return webStorage()?.getItem(key) ?? memory.get(key) ?? null;
  },
  set(key: string, value: string): void {
    const storage = webStorage();
    if (storage) storage.setItem(key, value);
    else memory.set(key, value);
  },
  remove(key: string): void {
    webStorage()?.removeItem(key);
    memory.delete(key);
  },
};

/** The keys the app stores, named once so a typo cannot silently lose a value. */
export const sessionKeys = {
  returnTo: 'humbugg:returnTo',
  // The PKCE verifier and CSRF state, which have to survive the full-page
  // navigation to the hosted sign-in page and back. Web-only in practice: the
  // native flow never leaves `promptAsync`, so it keeps them in the request
  // object instead.
  oauthVerifier: 'humbugg:oauthVerifier',
  oauthState: 'humbugg:oauthState',
  invite: (groupId: string) => `humbugg:invite:${groupId}`,
  join: (groupId: string) => `humbugg:join:${groupId}`,
} as const;
