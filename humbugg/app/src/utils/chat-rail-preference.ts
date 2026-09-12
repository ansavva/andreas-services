// Whether the chat rail is folded away, remembered across pages and restarts.
//
// The same shape as `theme-preference.ts`: AsyncStorage, one slot, and the default IS the absence
// of the key. Open is the default, so only "closed" is ever written and opening removes it.
import AsyncStorage from '@react-native-async-storage/async-storage';

export const CHAT_RAIL_KEY = 'humbugg.chat.rail';

export const chatRailPreference = {
  /** True unless the reader folded it away. */
  async loadOpen(): Promise<boolean> {
    try {
      return (await AsyncStorage.getItem(CHAT_RAIL_KEY)) !== 'closed';
    } catch {
      return true;
    }
  },

  async saveOpen(open: boolean): Promise<void> {
    try {
      if (open) await AsyncStorage.removeItem(CHAT_RAIL_KEY);
      else await AsyncStorage.setItem(CHAT_RAIL_KEY, 'closed');
    } catch {
      /* the rail still moves; only the memory of it is lost */
    }
  },
};
