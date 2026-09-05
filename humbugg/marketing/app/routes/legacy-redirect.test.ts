import { describe, expect, it } from 'vitest';

import { loader } from './legacy-redirect';

function redirectFor(path: string) {
  const response = loader({ request: new Request(`https://www.humbugg.com${path}`) });
  return { status: response.status, location: response.headers.get('Location') };
}

describe('legacy product-path redirects', () => {
  it.each([
    ['/login', 'https://app.humbugg.com/login'],
    ['/join/abc123', 'https://app.humbugg.com/join/abc123'],
  ])('permanently redirects %s to %s', (path, target) => {
    expect(redirectFor(path)).toEqual({ status: 301, location: target });
  });

  it('carries the query string across', () => {
    expect(redirectFor('/login?email=a%40b.com').location).toBe(
      'https://app.humbugg.com/login?email=a%40b.com',
    );
  });
});
