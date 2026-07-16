import { describe, expect, it } from 'vitest';

import { CANONICAL_ORIGIN, canonicalUrl } from './site';

describe('canonical site URLs', () => {
  it('default to the humbugg.com apex', () => {
    expect(CANONICAL_ORIGIN).toBe('https://humbugg.com');
    expect(canonicalUrl('/signup')).toBe('https://humbugg.com/signup');
  });
});
