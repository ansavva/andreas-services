// Which scheme the app paints — one decision, made in one place.
//
// Until 0.22.0 there was no place to make it. The design system's native leaves
// resolved their colours from `useColorScheme()`, which reports the OS and
// nothing else, and react-native-web ships no `Appearance.setColorScheme` to
// move it — so an in-app switch could repaint Humbugg's own surfaces and leave
// every Button, Field and Input from the package on the system setting. One
// screen, two schemes. `ThemeProvider`'s `scheme` prop is the seam that closes
// it, and this provider is the single thing that drives both halves:
//
//   • the package's leaves, through `ThemeProvider`'s `scheme`;
//   • Humbugg's own sheets, through `useResolvedScheme()` in `theme/styles.ts`.
//
// THERE IS EXACTLY ONE SUBSCRIPTION TO THE DEVICE IN THE APP and it is
// `useSystemScheme` below, held by the provider. Nothing else reads the OS —
// not Humbugg's screens, which take `resolved` from this context, and not the
// package's leaves, which are handed an explicit `scheme`. Two components each
// asking the device separately is how one screen ends up in two schemes, and
// `useSystemScheme`'s comment records the measurement that proved it.
//
// FIRST PAINT IS HELD, not corrected. The stored preference is read
// asynchronously, so rendering the tree before it arrives would paint the OS's
// scheme and then swap — a flash of the wrong app, worst for the reader who
// chose dark precisely because the bright one hurts. `children` therefore
// render only once `loaded` is true, joining the same gate the fonts already
// hold in `app/_layout.tsx`.
import { ThemeProvider } from '@ansavva/design-system';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Appearance } from 'react-native';

import { themePreference, type SchemePreference } from '../utils/theme-preference';

import { humbuggTheme, type Scheme } from './theme';

export type { SchemePreference };

interface SchemePreferenceContextValue {
  preference: SchemePreference;
  /** What `preference` comes to, with the device consulted where it defers to it. */
  resolved: Scheme;
  setPreference(next: SchemePreference): void;
  /** False until the stored choice has been read. Nothing paints before it is true. */
  loaded: boolean;
}

/**
 * `null` outside a provider, and that is a supported state rather than an
 * oversight: a jest test renders one screen, and a screen has no business
 * requiring the whole root layout to say what colour a card is. Everything
 * below falls back to `system`, which is the OS — exactly the behaviour every
 * component had before the switch existed.
 */
const SchemePreferenceContext = createContext<SchemePreferenceContextValue | null>(null);

/**
 * The scheme to paint, right now — read from the provider, not from the device.
 *
 * The provider holds the app's ONE subscription to the device and hands the
 * answer down; nothing else subscribes. That is not tidiness — with a
 * subscription per component, a live OS change reached some of them and not
 * others and half the screen repainted. `useSystemScheme` has the measurement.
 *
 * Outside a provider it reads the device directly — once, at render, with no
 * subscription. That is a jest test rendering one screen, or a component
 * mounted outside the app's root; neither has an app around it to repaint, so
 * following a change it will never see would buy nothing and would put the
 * second subscription back.
 */
export function useResolvedScheme(): Scheme {
  const context = useContext(SchemePreferenceContext);
  return context ? context.resolved : normalize(Appearance.getColorScheme());
}

/** The preference, what it currently resolves to, and how to change it. */
export function useSchemePreference(): {
  preference: SchemePreference;
  resolved: Scheme;
  setPreference(next: SchemePreference): void;
} {
  const context = useContext(SchemePreferenceContext);
  const resolved = useResolvedScheme();
  return {
    preference: context?.preference ?? 'system',
    resolved,
    // Outside a provider there is nothing to change; a no-op keeps a screen
    // rendered on its own from throwing on a press.
    setPreference: context?.setPreference ?? noop,
  };
}

/** Anything the platform reports that is not `dark` is light — including `null`. */
function normalize(scheme: string | null | undefined): Scheme {
  return scheme === 'dark' ? 'dark' : 'light';
}

/**
 * The device's own setting, subscribed to ONCE.
 *
 * This is react-native's `useColorScheme()` with one difference — the empty
 * dependency array — and the difference is the whole reason the hook is
 * rewritten here rather than imported. React Native Web's version re-subscribes
 * on EVERY render: its effect carries no dependency array, so each commit
 * removes its `MediaQueryList` listener and adds a fresh one. When the OS
 * scheme changes, the listeners already running re-render the tree, and the
 * subscriptions that have not been called yet are torn down mid-dispatch and
 * never hear about it.
 *
 * Measured on the stubbed export: a change from dark to light reached 68 of the
 * app's subscriptions and missed 6, and the one that reliably missed was the
 * PROVIDER'S — effects run child-first, so the outermost subscriber's listener
 * is the last one added and the last one dispatched, which is exactly the one a
 * re-render mid-dispatch removes. The whole app's scheme hung off it, so
 * "System" stopped following the device while the rest of the screen followed
 * it. Subscribing once, at mount, cannot be raced: this listener is never
 * removed and re-added, so it is never missing when the event arrives.
 *
 * It is also why `ThemeProvider` below is given an explicit `scheme` rather than
 * being left to consult the OS itself — that would put the package's leaves
 * back on the racing hook, one subscription each.
 */
function useSystemScheme(): Scheme {
  const [scheme, setScheme] = useState<Scheme>(() => normalize(Appearance.getColorScheme()));

  useEffect(() => {
    const subscription = Appearance.addChangeListener(({ colorScheme }) => {
      setScheme(normalize(colorScheme));
    });
    // A change between the first render and this effect would otherwise be lost.
    setScheme(normalize(Appearance.getColorScheme()));
    return () => subscription.remove();
  }, []);

  return scheme;
}

function noop(): void {}

export function SchemePreferenceProvider({ children }: { children: ReactNode }): ReactNode {
  const [preference, setStored] = useState<SchemePreference>('system');
  const [loaded, setLoaded] = useState(false);
  // The app's only read of the device setting.
  const system = useSystemScheme();
  const resolved: Scheme = preference === 'system' ? system : preference;

  useEffect(() => {
    let alive = true;
    void themePreference.load().then((stored) => {
      if (!alive) return;
      setStored(stored);
      setLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  // The write is fire-and-forget: the repaint is React's, and a storage that
  // refuses must not make the switch feel broken.
  const setPreference = useCallback((next: SchemePreference) => {
    setStored(next);
    void themePreference.save(next);
  }, []);

  const value = useMemo(
    () => ({ preference, resolved, setPreference, loaded }),
    [preference, resolved, setPreference, loaded],
  );

  return (
    <SchemePreferenceContext.Provider value={value}>
      {/*
        ALWAYS EXPLICIT, including when the reader follows the device.

        0.22.0's contract says an omitted `scheme` keeps the package on the OS,
        which is what the app did before this file existed — but taking that
        default would give the package its own subscription to the device, one
        per leaf, on exactly the hook `useSystemScheme` documents as racy. Under
        a forced scheme the package never consults the OS at all. `resolved` is
        the same value it would have computed, arrived at once, so the two
        halves cannot drift and there is one answer to "what scheme is this".
      */}
      <ThemeProvider theme={humbuggTheme} scheme={resolved}>
        {loaded ? children : null}
      </ThemeProvider>
    </SchemePreferenceContext.Provider>
  );
}
