import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const source = await readFile(new URL('./canonical_redirect.js', import.meta.url), 'utf8');
const handler = vm.runInNewContext(`${source}\nhandler;`);

function event(host, uri = '/', query) {
  return {
    request: {
      method: 'GET',
      uri,
      headers: { host: { value: host } },
      querystring: {},
      rawQueryString: () => query,
    },
  };
}

test('canonical requests continue to the selected origin', () => {
  const request = event('www.humbugg.com', '/terms').request;
  assert.equal(handler({ request }), request);
});

test('the apex redirects to www', () => {
  const response = handler(event('humbugg.com', '/privacy'));
  assert.equal(response.statusCode, 308);
  assert.equal(response.headers.location.value, 'https://www.humbugg.com/privacy');
});

test('legacy requests permanently redirect with the exact path and query', () => {
  const response = handler(event('humbugg.andreas.services', '/join/group-id', 'invite=abc%2F123&source=old'));
  assert.equal(response.statusCode, 308);
  assert.equal(response.headers.location.value, 'https://www.humbugg.com/join/group-id?invite=abc%2F123&source=old');
});

// Invite links carry their secret in the URL fragment, which a browser never
// sends to the origin and re-applies to the redirect target on its own. The
// function therefore cannot see it — the guarantee we can assert is that the
// path survives untouched, which is what keeps the fragment attached to the
// right URL.
test('a legacy invite path is preserved exactly so the fragment still lands on it', () => {
  const response = handler(event('humbugg.com', '/join/group-id'));
  assert.equal(response.headers.location.value, 'https://www.humbugg.com/join/group-id');
});

test('a bare apex request keeps the root path', () => {
  const response = handler(event('humbugg.com', '/'));
  assert.equal(response.headers.location.value, 'https://www.humbugg.com/');
});
