// A real session on the per-machine dev stack, minted from the dev-user.sh account.
//
// The dev Cognito app client allows only SRP (no USER_PASSWORD or ADMIN flows — the
// same posture as prod), so this uses amazon-cognito-identity-js to run actual SRP
// rather than asking anyone to weaken the client's auth flows for testing.
//
// Used by capture-fixtures.mjs (a bearer token to record fixtures with) and by
// live-setup.mjs (tokens to seed the browser's token store in E2E_LIVE mode).
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import pkg from 'amazon-cognito-identity-js';

const { CognitoUserPool, CognitoUser, AuthenticationDetails } = pkg;

function parseEnvFile(file) {
  const values = {};
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const separator = trimmed.indexOf('=');
    if (separator <= 0) continue;
    values[trimmed.slice(0, separator).trim()] = trimmed.slice(separator + 1).trim();
  }
  return values;
}

// The one per-machine file: pool and client from dev-aws-setup.sh, account from
// dev-user.sh. Same resolution as scripts/dev-aws-common.sh, XDG_CONFIG_HOME first.
export const DEV_ENV_FILE = path.join(
  process.env.XDG_CONFIG_HOME || path.join(homedir(), '.config'),
  'andreas-services', 'humbugg', 'dev.env');

export function devStackConfig() {
  let env;
  try {
    env = parseEnvFile(DEV_ENV_FILE);
  } catch {
    throw new Error(`${DEV_ENV_FILE} not found — run humbugg/scripts/dev-aws-setup.sh, then dev-user.sh.`);
  }
  const config = {
    userPoolId: env.COGNITO_USER_POOL_ID,
    clientId: env.COGNITO_CLIENT_ID,
    email: env.HUMBUGG_DEV_USER_EMAIL,
    password: env.HUMBUGG_DEV_USER_PASSWORD,
  };
  for (const [key, value] of Object.entries(config)) {
    if (!value) throw new Error(`dev-stack config is missing ${key} — refresh with dev-aws-setup.sh / dev-user.sh.`);
  }
  return config;
}

/** Signs in over SRP; resolves { accessToken, idToken, refreshToken }. */
export function devTokens() {
  const { userPoolId, clientId, email, password } = devStackConfig();
  const user = new CognitoUser({
    Username: email,
    Pool: new CognitoUserPool({ UserPoolId: userPoolId, ClientId: clientId }),
  });
  return new Promise((resolve, reject) => {
    user.authenticateUser(new AuthenticationDetails({ Username: email, Password: password }), {
      onSuccess: (session) =>
        resolve({
          accessToken: session.getAccessToken().getJwtToken(),
          idToken: session.getIdToken().getJwtToken(),
          refreshToken: session.getRefreshToken().getToken(),
        }),
      onFailure: reject,
      newPasswordRequired: () =>
        reject(new Error('The dev account demands a new password — re-run humbugg/scripts/dev-user.sh.')),
    });
  });
}
