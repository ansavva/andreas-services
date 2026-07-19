import { describe, expect, it } from 'vitest';

import { AVATAR_MAX_BYTES, avatarColor, initials, validateAvatarFile } from './avatar';

describe('initials', () => {
  it('takes the first letter of the first and last words', () => {
    expect(initials('Alex Rivera')).toBe('AR');
    expect(initials('  maya   lin  ')).toBe('ML');
  });

  it('uses a single initial for one-word names', () => {
    expect(initials('Sam')).toBe('S');
  });

  it('falls back to the email when there is no name', () => {
    expect(initials('', 'zoe@example.com')).toBe('Z');
    expect(initials(null, 'zoe@example.com')).toBe('Z');
  });

  it('returns a neutral placeholder when nothing is available', () => {
    expect(initials(null, null)).toBe('?');
    expect(initials('   ')).toBe('?');
  });
});

describe('avatarColor', () => {
  it('is deterministic for the same seed', () => {
    expect(avatarColor('Alex Rivera')).toEqual(avatarColor('Alex Rivera'));
  });

  it('always returns a background and a foreground', () => {
    const color = avatarColor('Theo');
    expect(color.bg).toMatch(/^#[0-9a-f]{6}$/i);
    expect(color.fg).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('handles an empty seed without throwing', () => {
    expect(() => avatarColor('')).not.toThrow();
    expect(() => avatarColor(null)).not.toThrow();
  });
});

describe('validateAvatarFile', () => {
  it('accepts a small PNG', () => {
    const file = new File([new Uint8Array(1024)], 'me.png', { type: 'image/png' });
    expect(validateAvatarFile(file)).toBeNull();
  });

  it('rejects a disallowed content type', () => {
    const file = new File([new Uint8Array(16)], 'me.gif', { type: 'image/gif' });
    expect(validateAvatarFile(file)).toMatch(/PNG, JPEG, or WebP/);
  });

  it('rejects a file larger than the size ceiling', () => {
    const file = new File([new Uint8Array(AVATAR_MAX_BYTES + 1)], 'big.png', { type: 'image/png' });
    expect(validateAvatarFile(file)).toMatch(/MB or smaller/);
  });
});
