// What the organizer was trying to do when Plus stopped them, remembered across Checkout.
//
// Deliberately NOT `sessionStore`. Everything that store holds dies with the tab or the process,
// which is right for a PKCE verifier and wrong here: Checkout leaves the app for a third-party
// origin and can take minutes — a card that asks for 3-D Secure hands the phone to a banking app,
// and the OS is free to evict this one while that happens. On web the return can also land in a
// different tab from the one that started it. AsyncStorage survives both, and there is nothing
// secret in an intent to record: it is one group id and one sentence of the app's own copy.
//
// It is a single slot, not a map. An organizer has one purchase in flight at a time — Plus is
// per-exchange and each Checkout is opened from one screen — so a second start replaces the first
// rather than accumulating rows nothing will ever clear.
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'humbugg.plus.intent';

export interface PlusIntent {
  /** The exchange the purchase is for. A return for any other group ignores this intent. */
  groupId: string;
  /**
   * What the organizer was blocked from doing, in the app's own words and already phrased to
   * follow "You can now…". Never the server's 402 message: that is written as a refusal.
   */
  action: string;
  /** Epoch milliseconds, so a forgotten intent can be aged out rather than resurfacing next season. */
  savedAt: number;
}

/** Older than this and the intent is stale — a Checkout nobody finished, or a much later return. */
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export const plusIntent = {
  async save(groupId: string, action: string): Promise<void> {
    try {
      await AsyncStorage.setItem(KEY, JSON.stringify({ groupId, action, savedAt: Date.now() }));
    } catch {
      // A browser refusing storage costs the resume line, not the purchase.
    }
  },

  /** The stored intent for this group, or null. Anything unparseable, foreign or stale reads null. */
  async load(groupId: string): Promise<PlusIntent | null> {
    try {
      const raw = await AsyncStorage.getItem(KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as Partial<PlusIntent>;
      if (typeof parsed?.groupId !== 'string' || typeof parsed.action !== 'string') return null;
      if (parsed.groupId !== groupId) return null;
      if (typeof parsed.savedAt !== 'number' || Date.now() - parsed.savedAt > MAX_AGE_MS) return null;
      return { groupId: parsed.groupId, action: parsed.action, savedAt: parsed.savedAt };
    } catch {
      return null;
    }
  },

  async clear(): Promise<void> {
    try {
      await AsyncStorage.removeItem(KEY);
    } catch {
      /* nothing to remove if nothing could be written */
    }
  },
};
