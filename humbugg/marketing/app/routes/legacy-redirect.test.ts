import { describe, expect, it } from 'vitest';

import { loader } from './legacy-redirect';

function redirectFor(path: string) {
  const response = loader({ request: new Request(`https://www.humbugg.com${path}`) });
  return { status: response.status, location: response.headers.get('Location') };
}

describe('legacy product-path redirects', () => {
  it.each([
    ['/login', 'https://app.humbugg.com/login'],
    ['/signup', 'https://app.humbugg.com/signup'],
    ['/confirm', 'https://app.humbugg.com/confirm'],
    ['/forgot-password', 'https://app.humbugg.com/forgot-password'],
    ['/join/abc123', 'https://app.humbugg.com/join/abc123'],
    ['/app', 'https://app.humbugg.com/'],
    ['/app/settings', 'https://app.humbugg.com/settings'],
    ['/app/groups/abc123', 'https://app.humbugg.com/groups/abc123'],
  ])('permanently redirects %s to %s', (path, target) => {
    expect(redirectFor(path)).toEqual({ status: 301, location: target });
  });

  it('carries the query string across', () => {
    expect(redirectFor('/confirm?email=a%40b.com').location).toBe(
      'https://app.humbugg.com/confirm?email=a%40b.com',
    );
  });
});
