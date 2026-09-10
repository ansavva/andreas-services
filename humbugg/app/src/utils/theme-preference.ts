// Which scheme the reader chose, remembered across restarts.
//
// The same shape as `plus-intent.ts`, and for the same reason: AsyncStorage
// survives a tab close and an OS eviction, and there is nothing secret in a
// choice of colours. One slot, not a map — a person has one appearance.
//
// `system` IS THE ABSENCE OF THE KEY, deliberately. The default is "follow the
// device", so writing `"system"` would record a preference that says the same
// thing as no preference at all — and leave a row behind for a reader who chose
// to stop expressing one. Choosing System removes the key; the privacy table
// says exactly that ("until you pick System or clear site data").
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { Scheme } from '../theme/theme';

export const THEME_KEY = 'humbugg.theme';

/** What the reader picked. `system` defers to the device. */
export type SchemePreference = 'system' | Scheme;

export const themePreference = {
  /** The stored preference, or `system` when nothing is stored or the value is unrecognised. */
  async load(): Promise<SchemePreference> {
    try {
      const raw = await AsyncStorage.getItem(THEME_KEY);
      return raw === 'light' || raw === 'dark' ? raw : 'system';
    } catch {
      // A browser refusing storage costs the memory of the choice, not the choice.
      return 'system';
    }
  },

  async save(preference: SchemePreference): Promise<void> {
    try {
      if (preference === 'system') await AsyncStorage.removeItem(THEME_KEY);
      else await AsyncStorage.setItem(THEME_KEY, preference);
    } catch {
      /* the app still repaints; only the memory of it is lost */
    }
  },
};
