// Playwright globalSetup for E2E_LIVE=1: mint a real dev-stack session once and park it
// where e2e/support/auth.ts seeds it into the browser's token store. The file is
// ignored by git and short-lived by nature (Cognito access tokens expire in an hour).
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { devTokens } from './dev-session.mjs';

export default async function liveSetup() {
  const tokens = await devTokens();
  const target = path.join(path.dirname(fileURLToPath(import.meta.url)), '.live-session.json');
  writeFileSync(target, JSON.stringify(tokens));
}
