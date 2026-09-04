import { describe, expect, it } from 'vitest';

import { loader } from './legacy-redirect';

function redirectFor(path: string) {
  const response = loader({ request: new Request(`https://www.humbugg.com${path}`) });
  return { status: response.status, location: response.headers.get('Location') };
}

describe('legacy product-path redirects', () => {
  it.each([
    ['/login', 'https://app.humbugg.com/login'],
    // Sign-up, confirm and forgot-password are all Managed Login's hosted
    // page now — the app has no screen for any of them but `/login`.
    ['/signup', 'https://app.humbugg.com/login'],
    ['/confirm', 'https://app.humbugg.com/login'],
    ['/forgot-password', 'https://app.humbugg.com/login'],
    ['/join/abc123', 'https://app.humbugg.com/join/abc123'],
    ['/app', 'https://app.humbugg.com/'],
    ['/app/settings', 'https://app.humbugg.com/settings'],
    ['/app/groups/abc123', 'https://app.humbugg.com/groups/abc123'],
  ])('permanently redirects %s to %s', (path, target) => {
    expect(redirectFor(path)).toEqual({ status: 301, location: target });
  });

  it('carries the query string across', () => {
    expect(redirectFor('/confirm?email=a%40b.com').location).toBe(
      'https://app.humbugg.com/login?email=a%40b.com',
    );
  });
});
