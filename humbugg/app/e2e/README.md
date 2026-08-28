# The app's browser tier

One Playwright suite, two modes, mirrored on studio's browser tier.

## Stubbed mode — `npm run e2e` (what CI runs)

The app is exported the way production exports it (`expo export -p web`, single-file
output) and served statically on :4173. Every `/api/**` request is answered from the
committed fixtures in `fixtures/` by `support/api-stub.ts`. No AWS, no credentials, no
dev stack — which is what lets this run in the PR workflow, which never writes to AWS.

Three details are load-bearing:

- **The export runs with `--clear`.** Metro's transform cache does not key on
  environment variables, so without it an export silently reuses whichever
  `EXPO_PUBLIC_*` values the previous export inlined (measured: identical bundle hash
  across env changes).
- **The Cognito values are fake but present.** Empty values flip `isAuthConfigured`
  and the app renders a different, unconfigured path — a suite against that screen is
  green and tests nothing.
- **The API base is `/api`**, so calls are same-origin and land squarely in the
  `**/api/**` route glob with no CORS in the way.

The stub answers unknown paths with **501 and the path in the body**, never `{}` — and
the two guard specs in `guards.spec.ts` ("no request escapes to the network", "nothing
5xxs") turn a missing fixture or an escaped request into a hard failure. Do not weaken
either; they are what makes the rest of the suite honest.

## Live mode — `npm run e2e:live` (local only)

The same specs against the Expo dev server on :8081 and the real dev backend on :5001:

```bash
./humbugg/scripts/dev-up.sh     # backend + app dev server
npm run e2e:live                # from humbugg/app
```

`globalSetup` (`support/live-setup.mjs`) signs in as the `dev-user.sh` account over
real SRP and seeds the browser with the resulting session. Specs that assert exact
fixture data skip themselves in live mode with a per-spec `stubOnly(...)` — never a
module-level `test.skip`, which silently skips a whole file.

## Auth seeding

`support/auth.ts` writes the token store the app itself reads on start — the exact
`humbugg.auth.*` localStorage keys `src/auth/oauth.ts` owns. Stubbed mode seeds
structurally valid, deliberately unsigned JWTs (the browser never verifies signatures;
every authorization decision is the backend's). There is no test flag compiled into
the app bundle, and there must never be one.

## Re-recording fixtures

```bash
./humbugg/scripts/dev-up-backend.sh    # the API on :5001
npm run e2e:capture                    # from humbugg/app
```

`support/capture-fixtures.mjs` converges its own seed data (profile, one exchange, one
wish) on the dev stack, captures the GET responses, scrubs invite secrets and presigned
URLs, and **asserts the scrub held** before writing. Do not capture a fixture with
`curl` — the scrubbing is the reason this script exists.
