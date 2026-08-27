/**
 * Two modes, one suite.
 *
 *   default      every `/api/**` fulfilled from fixtures captured off the real
 *                API. No AWS, no credentials, no stack, deterministic — this is
 *                what runs in `studio-pr.yml`.
 *   E2E_LIVE=1   the same specs against `scripts/dev-up.sh` and this machine's
 *                seeded dev stack. Local only, never in CI.
 *
 * The stubbed mode builds and serves the app itself. It builds WITHOUT
 * `VITE_COGNITO_*`, so Amplify is not configured and reaches no network — the
 * session comes from `support/session.ts`, which seeds the token store Amplify
 * reads rather than putting a test flag in the app.
 */
import { defineConfig, devices } from "@playwright/test";

import { CLIENT_ID, POOL_ID } from "./e2e/support/session";

const live = process.env.E2E_LIVE === "1";

export default defineConfig({
  testDir: "./e2e",
  // A failing e2e is a bug or a bad spec; a retry hides which. Nothing here is
  // timing-dependent by design.
  retries: 0,
  fullyParallel: true,
  reporter: process.env.CI ? "list" : [["list"], ["html", { open: "never" }]],
  // In LIVE mode the specs that stub `/api/**` are skipped by the fixture
  // itself; what stays meaningful is the rendering and the addressing.
  use: {
    baseURL: live ? "http://localhost:5173" : "http://localhost:4173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // In LIVE mode the developer already has `dev-up.sh` running; starting a
  // second server on top of it would bind-clash and the failure would read as a
  // test problem rather than a "you forgot the API" problem.
  webServer: live
    ? undefined
    : {
        command: "npm run build && npm run preview -- --port 4173 --strictPort",
        url: "http://localhost:4173",
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
        env: {
          // A pool that does not exist. Amplify must be CONFIGURED — with
          // these empty the app renders "Auth is not configured" instead of
          // anything testable — but it is never contacted, because the token
          // store `support/session.ts` seeds answers first. The client id has
          // to match the one those localStorage keys are written under.
          VITE_COGNITO_USER_POOL_ID: POOL_ID,
          VITE_COGNITO_CLIENT_ID: CLIENT_ID,
          // Empty on purpose: the app then calls `/api/...` same-origin, which
          // is exactly what `page.route("**/api/**")` intercepts. A base URL
          // here would send the request somewhere the route glob still catches,
          // but at an origin nothing is serving — a slower way to the same
          // place, and confusing when a stub is missing.
          VITE_API_URL: "",
        },
      },
});
