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
  const request = event('humbugg.com', '/app').request;
  assert.equal(handler({ request }), request);
});

test('legacy requests permanently redirect with the exact path and query', () => {
  const response = handler(event('humbugg.andreas.services', '/join/group-id', 'invite=abc%2F123&source=old'));
  assert.equal(response.statusCode, 308);
  assert.equal(response.headers.location.value, 'https://humbugg.com/join/group-id?invite=abc%2F123&source=old');
});

test('www redirects to the apex without inventing a query marker', () => {
  const response = handler(event('www.humbugg.com', '/signup'));
  assert.equal(response.statusCode, 308);
  assert.equal(response.headers.location.value, 'https://humbugg.com/signup');
});
