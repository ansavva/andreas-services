import { defineConfig, devices } from '@playwright/test';

// One suite, two modes — mirrored on studio's browser tier.
//
// Stubbed (default, what CI runs): the app is exported the way production exports it and
// served statically; every `/api/**` request is answered from committed fixtures by
// `e2e/support/api-stub.ts`. No AWS, no credentials, no dev stack — which is what lets
// this live in a PR workflow that never writes to AWS.
//
// Live (`E2E_LIVE=1`, local only): the same specs against the Expo dev server on :8081
// and the real dev backend on :5001 (`dev-up.sh`), signed in as the dev-user.sh account.
// Nothing here bills, so live mode is an ordinary local mode, not a guarded one.
const live = process.env.E2E_LIVE === '1';

export default defineConfig({
  testDir: './e2e',
  // A failing e2e is a bug or a bad spec; a retry hides which.
  retries: 0,
  fullyParallel: true,
  reporter: process.env.CI ? 'list' : [['list'], ['html', { open: 'never' }]],
  globalSetup: live ? './e2e/support/live-setup.mjs' : undefined,
  use: {
    baseURL: live ? 'http://localhost:8081' : 'http://localhost:4173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: live
    ? undefined
    : {
        // `serve -s` gives the SPA fallback the single-file web export needs for deep
        // links like /groups/:id. The export env matters:
        //  - API base "/api" makes every call same-origin, so page.route's `**/api/**`
        //    glob catches all of it with no CORS in the way (studio's VITE_API_URL="" trick);
        //  - the Cognito values are fake but PRESENT, because empty values flip
        //    `isAuthConfigured` and the app renders a different (unconfigured) path.
        //  - `--clear` is not optional: Metro's transform cache does not key on env, so
        //    without it an export silently reuses whichever EXPO_PUBLIC_* values the
        //    previous export inlined (measured: same bundle hash across env changes).
        command:
          'npx expo export -p web --output-dir dist-e2e --clear && npx serve -s dist-e2e -l 4173 --no-clipboard',
        url: 'http://localhost:4173',
        reuseExistingServer: !process.env.CI,
        timeout: 300_000,
        env: {
          EXPO_PUBLIC_API_BASE_URL: '/api',
          EXPO_PUBLIC_COGNITO_CLIENT_ID: 'e2e-fake-client',
          EXPO_PUBLIC_COGNITO_DOMAIN: 'e2e-fake.auth.us-east-1.amazoncognito.com',
        },
      },
});
