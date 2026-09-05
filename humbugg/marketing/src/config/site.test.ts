import { describe, expect, it } from 'vitest';

import { APP_ORIGIN, CANONICAL_ORIGIN, appUrl, canonicalUrl } from './site';

describe('canonical site URLs', () => {
  it('default to the humbugg.com www host', () => {
    expect(CANONICAL_ORIGIN).toBe('https://www.humbugg.com');
    expect(canonicalUrl('/terms')).toBe('https://www.humbugg.com/terms');
  });
});

describe('product app URLs', () => {
  it('default to the app subdomain', () => {
    expect(APP_ORIGIN).toBe('https://app.humbugg.com');
    expect(appUrl('/login')).toBe('https://app.humbugg.com/login');
  });
});
