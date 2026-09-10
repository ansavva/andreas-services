#!/usr/bin/env node
// Mints a real session for the production smoke account, for the post-deploy
// `smoke-test` job in .github/workflows/humbugg-prod.yaml (#642, #586).
//
// Every Humbugg test tier stops short of API Gateway: the unit tiers fake the
// repositories, the browser suite answers `/api/**` from committed fixtures, and
// the live browser tier talks to a local backend with no gateway in front of it.
// So the gateway's authorizer — the thing that 401ed two `[AllowAnonymous]`
// endpoints for their entire lives (#582) — is exercised by nothing until a
// change is already serving. The anonymous half of that gap is covered by the
// bare curls in the smoke job; the authenticated half needs a real token, which
// needs a real account, which is what this script signs in as.
//
// SRP, not USER_PASSWORD: the prod app client allows exactly one auth flow,
// ALLOW_USER_SRP_AUTH, and holds no client secret. Weakening the client so a
// test could use a simpler flow would make the test's posture differ from every
// real sign-in — the opposite of what a smoke test is for. The logic below is
// app/e2e/support/dev-session.mjs with the file-reading removed: this runs on a
// CI runner, where the four inputs arrive as environment variables.
//
// Output contract: exactly one line of JSON on stdout, nothing else, ever.
//   {"accessToken":"…","idToken":"…"}
// The caller reads that line, masks both values, and never echoes them. Errors
// go to stderr and name the missing variable — never its value. This repo is
// public and this script's output lands in a public workflow log.
//
// Usage:
//   npm ci --prefix humbugg/scripts        # 22 packages, under a second
//   HUMBUGG_SMOKE_USER_EMAIL=… HUMBUGG_SMOKE_USER_PASSWORD=… \
//   COGNITO_USER_POOL_ID=… COGNITO_CLIENT_ID=… \
//     node humbugg/scripts/smoke-session.mjs
import pkg from 'amazon-cognito-identity-js';

const { CognitoUserPool, CognitoUser, AuthenticationDetails } = pkg;

const REQUIRED = [
  'HUMBUGG_SMOKE_USER_EMAIL',
  'HUMBUGG_SMOKE_USER_PASSWORD',
  'COGNITO_USER_POOL_ID',
  'COGNITO_CLIENT_ID',
];

function readConfig() {
  // Named, not printed. An empty GitHub secret arrives as an empty string rather
  // than an absent key — a fork or a PR context sees exactly that — so the check
  // is on the trimmed value, not on presence.
  const missing = REQUIRED.filter((name) => !(process.env[name] ?? '').trim());
  if (missing.length > 0) {
    throw new Error(`missing or empty environment variable(s): ${missing.join(', ')}`);
  }
  return {
    email: process.env.HUMBUGG_SMOKE_USER_EMAIL.trim(),
    password: process.env.HUMBUGG_SMOKE_USER_PASSWORD,
    userPoolId: process.env.COGNITO_USER_POOL_ID.trim(),
    clientId: process.env.COGNITO_CLIENT_ID.trim(),
  };
}

/** Signs in over SRP; resolves { accessToken, idToken }. */
function smokeTokens({ email, password, userPoolId, clientId }) {
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
        }),
      onFailure: reject,
      // The account is created with a permanent password precisely so this
      // branch never fires; if it does, the password was reset rather than set.
      newPasswordRequired: () =>
        reject(
          new Error(
            'the smoke account is in FORCE_CHANGE_PASSWORD — reset it with ' +
              '`aws cognito-idp admin-set-user-password … --permanent` and update ' +
              'the HUMBUGG_SMOKE_USER_PASSWORD secret.',
          ),
        ),
      // No MFA is configured on the pool; if one ever is, this says so plainly
      // rather than hanging until the job times out.
      mfaRequired: () => reject(new Error('the smoke account requires MFA, which this script cannot satisfy.')),
      totpRequired: () => reject(new Error('the smoke account requires TOTP, which this script cannot satisfy.')),
    });
  });
}

try {
  const tokens = await smokeTokens(readConfig());
  process.stdout.write(`${JSON.stringify(tokens)}\n`);
} catch (error) {
  // `name: message` only. Cognito's failure messages carry no credential
  // material ("Incorrect username or password."), and a stack trace would add
  // nothing a workflow log should hold.
  const name = error?.name ?? 'Error';
  const message = error?.message ?? String(error);
  process.stderr.write(`smoke-session: ${name}: ${message}\n`);
  process.exit(1);
}
