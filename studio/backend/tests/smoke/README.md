# `tests/smoke/` — the deployed prod API, after it is already live

Five tests that sign in to the real Cognito pool and drive
`studio-api.andreas.services` over HTTPS. `studio-prod.yaml` runs them in the
`smoke` job, after `update-lambda`. One-time setup:
[`../../../docs/PROD_SMOKE.md`](../../../docs/PROD_SMOKE.md).

## What it is not

**It is not a gate.** Studio has no staging environment — the prod workflow
deploys straight to production — so by the time this runs, the new image is
already serving every request. Nothing here prevents a bad deploy from reaching
anyone. It fails the workflow because red is the signal: the point is that a
broken deploy announces itself in minutes with a named cause, instead of weeks
later through whoever opened the site.

**It is not a functional suite.** `tests/` covers behaviour, against moto, in
seconds. This asserts a handful of end-to-end shapes and stops, because every
assertion here costs a round trip to a real API and writes real rows.

## What it catches that nothing else can

**The Lambda's own execution role.** moto does not enforce IAM at all — the
backend suite passes against a policy granting nothing — and
`tests/integration/` runs Flask in-process under a developer's credentials,
which are far wider than the function's. Only a call made *by the deployed
function* proves the deployed function may make it. `dynamodb:BatchGetItem`
missing from the API role shipped exactly through that gap: sign-in kept working
because membership resolves with a `Query`, and every folder listing returned
"Could not read the catalog".

**An empty listing would not have caught it**, which is why every listing
asserted on here has a child in it: `catalog.records([])` short-circuits and
issues no `BatchGetItem`.

It also covers what only a deployed stack has: API Gateway in front of Mangum in
front of Flask, the custom domain and its certificate, the Lambda's environment
(set by `update-lambda`, not by Terraform), a real ID token from the real pool,
and a presigned URL signed by the function's rotating credentials and then
actually fetched.

## What it still cannot catch

The SPA — nothing here loads `studio.andreas.services`, runs a bundle or drives
a browser, so a broken frontend build, a CORS preflight answered by API Gateway,
or an Amplify sign-in that no longer completes all pass unnoticed. Anything
behind a grant this account's own requests never need. And anything that only
goes wrong at a size this deliberately does not reach: the body it uploads is
under a hundred bytes, so nothing here says a 300 MB clip still works.

## The one library

The account is a member of **exactly one** library, seeded from
[`../../../seeds/smoke.json`](../../../seeds/smoke.json). That is what keeps
this suite away from everything else in the catalog, and it is structural rather
than careful: `app_factory`'s `before_request` resolves the library a request is
about from the caller's own membership rows, so a caller with one membership can
only ever address that one, and every route then checks the node's own `lib`
against the same rows.

Three things hold it up, and changing any of them needs the others revisited:

1. The seeder writes one membership, never any other, and **refuses to finish**
   if it reads back a second.
2. No request in this suite sends `X-Studio-Library` — the header is the only
   way one of these calls could name a different library.
3. `only_library` asserts the list before any fixture writes, and
   `test_the_smoke_account_reaches_exactly_one_library` asserts it again as a
   named test, so a violation is a failing test and not a collection error.

## Running it

**CI only, in practice.** `studio-prod.yaml` passes the base URL, the pool and
client ids, and the password from the `studio-production` environment secret.
There is no local wrapper on purpose: a local run needs that production secret
in a developer's shell for a run CI already does every deploy.

Nothing has a default. Without `STUDIO_SMOKE=1` the whole tree is skipped at
collection — a `poetry run pytest -q` on a laptop reports them as skips and
touches nothing — and with it, a missing variable fails by name before a single
request is made.

| Variable | |
|---|---|
| `STUDIO_SMOKE=1` | The collection gate. |
| `STUDIO_SMOKE_BASE_URL` | The origin under test, e.g. the deployed API's. |
| `STUDIO_SMOKE_POOL_ID` / `STUDIO_SMOKE_CLIENT_ID` | The pool to sign in against. |
| `SMOKE_TEST_USER_PASSWORD` | The only credential. No default, ever. |

No AWS credentials are needed or used: the suite holds a pool id, a client id,
an address and a password, and reaches everything else over HTTPS. That is also
what makes it exercise the function's role rather than a developer's.

## Before changing a test

- **`sign_in.py` can only ever sign in as the smoke account.** Its address comes
  from the fixture and is not an input. Keep it that way — studio has no
  supported way to hold a production token for a person, and this must not
  become one.
- **Everything created must be created under `scratch`**, which is deleted at
  session teardown however the run ends, and swept at setup if a killed job left
  one behind.
