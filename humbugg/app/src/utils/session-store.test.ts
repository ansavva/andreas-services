import { Platform } from 'react-native';

import { sessionKeys, sessionStore } from './session-store';

// The one seam that hides "there is no sessionStorage on a device": browser storage on
// web, a module-level map on native. These tests pin both sides and the Safari branch.

describe('sessionStore', () => {
  const originalOS = Platform.OS;

  afterEach(() => {
    Object.defineProperty(Platform, 'OS', { value: originalOS, configurable: true });
    delete (globalThis as { sessionStorage?: unknown }).sessionStorage;
    sessionStore.remove('k');
  });

  it('uses the in-memory map on native', () => {
    Object.defineProperty(Platform, 'OS', { value: 'ios', configurable: true });
    sessionStore.set('k', 'v');
    expect(sessionStore.get('k')).toBe('v');
    sessionStore.remove('k');
    expect(sessionStore.get('k')).toBeNull();
  });

  it('uses sessionStorage on web so a real reload survives', () => {
    Object.defineProperty(Platform, 'OS', { value: 'web', configurable: true });
    const backing = new Map<string, string>();
    (globalThis as { sessionStorage?: unknown }).sessionStorage = {
      getItem: (key: string) => backing.get(key) ?? null,
      setItem: (key: string, value: string) => void backing.set(key, value),
      removeItem: (key: string) => void backing.delete(key),
    };

    sessionStore.set('k', 'v');
    expect(backing.get('k')).toBe('v');
    expect(sessionStore.get('k')).toBe('v');
    sessionStore.remove('k');
    expect(backing.has('k')).toBe(false);
  });

  it('falls back to memory when Safari throws on sessionStorage access', () => {
    Object.defineProperty(Platform, 'OS', { value: 'web', configurable: true });
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      get() {
        throw new Error('SecurityError');
      },
    });

    // Must neither throw nor lose the value.
    sessionStore.set('k', 'v');
    expect(sessionStore.get('k')).toBe('v');
    sessionStore.remove('k');
    expect(sessionStore.get('k')).toBeNull();
  });

  it('names every stored key once', () => {
    // A typo in a key silently loses an invite secret; the registry is the guard.
    expect(sessionKeys.returnTo).toBe('humbugg:returnTo');
    expect(sessionKeys.invite('g1')).toBe('humbugg:invite:g1');
    expect(sessionKeys.join('g1')).toBe('humbugg:join:g1');
  });
});
