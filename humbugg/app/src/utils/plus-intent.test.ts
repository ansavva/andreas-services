// The resume intent survives a trip to Stripe, and only ever comes back for the exchange and the
// day it was written for. A stale one is worse than none: "You can now invite everyone waiting"
// on next season's exchange is a promise about the wrong group.
import AsyncStorage from '@react-native-async-storage/async-storage';

import { plusIntent } from './plus-intent';

const storage = AsyncStorage as jest.Mocked<typeof AsyncStorage>;

function stored(value: string | null) {
  storage.getItem.mockResolvedValue(value);
}

describe('plusIntent', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    storage.setItem.mockResolvedValue(undefined);
    storage.removeItem.mockResolvedValue(undefined);
  });

  it('round-trips the action for the exchange it was saved for', async () => {
    await plusIntent.save('g1', 'invite everyone else who is waiting to join');
    const [key, body] = storage.setItem.mock.calls[0] as [string, string];
    expect(key).toBe('humbugg.plus.intent');

    stored(body);
    await expect(plusIntent.load('g1')).resolves.toMatchObject({
      groupId: 'g1',
      action: 'invite everyone else who is waiting to join',
    });
  });

  it('ignores an intent belonging to another exchange', async () => {
    stored(JSON.stringify({ groupId: 'g2', action: 'anything', savedAt: Date.now() }));
    await expect(plusIntent.load('g1')).resolves.toBeNull();
  });

  it('ignores an intent older than a day', async () => {
    stored(
      JSON.stringify({
        groupId: 'g1',
        action: 'anything',
        savedAt: Date.now() - 25 * 60 * 60 * 1000,
      }),
    );
    await expect(plusIntent.load('g1')).resolves.toBeNull();
  });

  it('reads nothing rather than throwing on a corrupt or empty slot', async () => {
    stored('not json');
    await expect(plusIntent.load('g1')).resolves.toBeNull();

    stored(JSON.stringify({ groupId: 'g1' }));
    await expect(plusIntent.load('g1')).resolves.toBeNull();

    stored(null);
    await expect(plusIntent.load('g1')).resolves.toBeNull();
  });

  it('survives a browser that refuses storage', async () => {
    storage.setItem.mockRejectedValue(new Error('QuotaExceededError'));
    await expect(plusIntent.save('g1', 'anything')).resolves.toBeUndefined();

    storage.getItem.mockRejectedValue(new Error('SecurityError'));
    await expect(plusIntent.load('g1')).resolves.toBeNull();
  });
});
