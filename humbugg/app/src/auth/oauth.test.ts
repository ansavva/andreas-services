// PKCE is not enforceable from Terraform.
//
// Cognito has no "require PKCE" switch on a user pool client: it accepts a bare
// authorization-code request from a public client just as happily as a
// challenged one. So the only thing standing between this app and an
// interceptable code is `createAuthRequest`, and the only way to keep that true
// is to assert the URL it actually produces rather than the config it was given.
//
// `state` is asserted for the same reason — it is the CSRF check the web
// callback route compares against, and losing it would fail silently.
//
// expo-crypto is replaced with Node's own SHA-256 because jest-expo's stub for
// it returns an EMPTY digest and all-zero randomness. Without this the challenge
// comes out falsy, expo-auth-session omits the parameter, and the test passes
// against a URL with no PKCE in it at all — the exact bug it exists to catch.
// Only the platform digest primitive is substituted: the request, the library
// and the URL under assertion are all real.
jest.mock('expo-crypto', () => {
  const nodeCrypto = require('node:crypto');
  return {
    CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
    CryptoEncoding: { BASE64: 'base64', HEX: 'hex' },
    getRandomValues: (array: Uint8Array) => nodeCrypto.webcrypto.getRandomValues(array),
    digestStringAsync: async (_algorithm: string, data: string, options: { encoding: string }) =>
      nodeCrypto.createHash('sha256').update(data).digest(options.encoding),
  };
});

import { createAuthRequest, discovery } from './oauth';

describe('the authorize request', () => {
  it('asks for a code with an S256 PKCE challenge and a state', async () => {
    const request = createAuthRequest('humbugg://auth/callback');
    const url = new URL(await request.makeAuthUrlAsync(discovery));

    expect(url.origin + url.pathname).toBe(discovery.authorizationEndpoint);
    expect(url.searchParams.get('client_id')).toBeTruthy();
    expect(url.searchParams.get('response_type')).toBe('code');
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    // A base64url SHA-256 digest: 43 characters, no padding, no '+' or '/'.
    expect(url.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(url.searchParams.get('state')).toBeTruthy();
    expect(url.searchParams.get('redirect_uri')).toBe('humbugg://auth/callback');
    expect(url.searchParams.get('scope')).toBe('openid email profile');

    // The verifier is what gets sent at the token exchange; a challenge without
    // one in hand would be theatre.
    expect(request.codeVerifier).toMatch(/^[A-Za-z0-9_.~-]{43,128}$/);
  });
});
