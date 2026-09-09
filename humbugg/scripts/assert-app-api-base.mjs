#!/usr/bin/env node
// Asserts the exported web bundle inlined an API base URL that includes the
// gateway's /api path prefix.
//
// Every application route on api.humbugg.com sits under `ANY /api/{proxy+}`
// (humbugg/infra/modules/compute/main.tf). A base URL of the bare origin
// therefore lands on no route at all, and API Gateway's own 404 carries no
// Access-Control-* headers — by design, since ASP.NET is the single source of
// them. The browser sees a failed preflight, so every call from app.humbugg.com
// fails as "Failed to fetch" with nothing transferred and no status to read.
//
// That shipped in #217 and stayed live: the value only exists in the deploy
// workflow's env block, the browser suite answers /api/** from fixtures behind a
// same-origin base, and no PR check crosses a real origin. Metro inlines
// EXPO_PUBLIC_* at build time, so the exported bundle is the only place the
// mistake is visible — which is what this reads.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const dist = process.argv[2];
if (!dist) {
  console.error('usage: assert-app-api-base.mjs <dist-dir>');
  process.exit(2);
}

const files = [];
(function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path);
    else if (path.endsWith('.js')) files.push(path);
  }
})(dist);

// Matches the inlined base URL and captures whatever path follows the origin.
const baseUrl = /https:\/\/api\.humbugg\.com(\/[A-Za-z0-9/_-]*)?/g;
const found = new Set();
for (const file of files) {
  for (const [, path] of readFileSync(file, 'utf8').matchAll(baseUrl)) {
    found.add(path ?? '');
  }
}

if (found.size === 0) {
  console.error(`No api.humbugg.com base URL found in ${dist}. The export did not inline one.`);
  process.exit(1);
}

const bad = [...found].filter((path) => !path.startsWith('/api'));
if (bad.length > 0) {
  console.error(
    `api.humbugg.com base URL is missing the /api prefix in ${dist}: ` +
      bad.map((path) => `"https://api.humbugg.com${path}"`).join(', ') +
      '.\nEvery route is behind ANY /api/{proxy+}; without the prefix the app 404s ' +
      'with no CORS headers and every request fails as "Failed to fetch".\n' +
      'Set EXPO_PUBLIC_API_BASE_URL to https://api.humbugg.com/api.',
  );
  process.exit(1);
}

console.log(`API base URL carries the /api prefix: ${[...found].map((p) => `https://api.humbugg.com${p}`).join(', ')}`);
