// Ported from the web app. `initials` and `avatarColor` are unchanged; the
// `validateAvatarFile` cases now build the plain `{ type, size }` descriptor the
// function takes, because there is no DOM `File` on this side.
import { AVATAR_MAX_BYTES, avatarColor, initials, toDataUrl, validateAvatarFile } from './avatar';

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
    expect(validateAvatarFile({ type: 'image/png', size: 1024 })).toBeNull();
  });

  it('rejects a disallowed content type', () => {
    expect(validateAvatarFile({ type: 'image/gif', size: 16 })).toMatch(/PNG, JPEG, or WebP/);
  });

  it('rejects a file larger than the size ceiling', () => {
    expect(validateAvatarFile({ type: 'image/png', size: AVATAR_MAX_BYTES + 1 })).toMatch(/MB or smaller/);
  });
});

describe('toDataUrl', () => {
  it('builds the data URL shape the upload endpoint parses', () => {
    expect(toDataUrl('image/png', 'AAAA')).toBe('data:image/png;base64,AAAA');
  });
});
