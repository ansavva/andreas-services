# End-to-end

Two modes, one set of specs.

```bash
npm run e2e            # stubbed. No AWS, no credentials, no stack. CI runs this.
npm run e2e:live       # the same specs against dev-up.sh and the seeded stack.
python e2e/fixtures/capture.py    # re-take the fixtures off the real API
```

## Why the fixtures are captured rather than written

They come from `http://localhost:8000` against the published dev-seed
character — the same 54-object fixture every developer's stack loads. A
hand-written stub drifts from the API silently and then asserts its own
imagination. `capture.py` is the only way they are produced, and it **scrubs
presigned URLs**: `/api/reel` answers with them, and a presigned URL carries the
signing key's access key id and a signature. The first capture put both straight
into git, and the browser then fetched real S3 for fourteen images — caught by
the spec that asserts nothing escapes to the network.

## Why there is no test flag in the app

`App.tsx` renders `<LoginForm />` unless `authenticated`, which comes from
Amplify. `support/session.ts` seeds the token store Amplify itself reads, so the
app is signed in without a backdoor compiled into the production bundle and
without Cognito being contacted. Amplify has to be *configured* for this — built
with the pool variables empty the app renders "Auth is not configured" instead,
which an early version of these specs happily passed against.

## Live mode

`E2E_LIVE=1` points the same specs at `http://localhost:5173`, so it needs
`scripts/dev-up.sh` running and a real browser session. It is a local check
before a risky change, never CI: CI has no dev stack and never writes to AWS.
