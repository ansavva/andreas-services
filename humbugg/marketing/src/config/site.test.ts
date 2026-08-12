import { describe, expect, it } from 'vitest';

import { APP_ORIGIN, CANONICAL_ORIGIN, appUrl, canonicalUrl, legacyAppPath } from './site';

describe('canonical site URLs', () => {
  it('default to the humbugg.com www host', () => {
    expect(CANONICAL_ORIGIN).toBe('https://www.humbugg.com');
    expect(canonicalUrl('/terms')).toBe('https://www.humbugg.com/terms');
  });
});

describe('product app URLs', () => {
  it('default to the app subdomain', () => {
    expect(APP_ORIGIN).toBe('https://app.humbugg.com');
    expect(appUrl('/signup')).toBe('https://app.humbugg.com/signup');
  });
});

describe('legacyAppPath', () => {
  it('keeps auth and join paths one-to-one', () => {
    expect(legacyAppPath('/login')).toBe('/login');
    expect(legacyAppPath('/forgot-password')).toBe('/forgot-password');
    expect(legacyAppPath('/join/abc123')).toBe('/join/abc123');
  });

  it('drops the /app prefix the product app no longer uses', () => {
    expect(legacyAppPath('/app')).toBe('/');
    expect(legacyAppPath('/app/')).toBe('/');
    expect(legacyAppPath('/app/settings')).toBe('/settings');
    expect(legacyAppPath('/app/groups/abc123')).toBe('/groups/abc123');
  });
});
