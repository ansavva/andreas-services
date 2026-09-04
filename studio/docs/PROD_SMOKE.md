# Prod smoke test — one-time setup

**One step by hand, once: a password.** After that the pipeline provisions its
own test identity on every deploy.

The post-deploy suite in [`../backend/tests/smoke/`](../backend/tests/smoke/README.md)
signs in to the real Cognito pool and drives `studio-api.andreas.services` over
HTTPS. It needs an account, that account needs a library — every route in this
service authorises against membership rows, so a caller in no library is refused
by `before_request` before any route runs — and both are hand-written rows the
catalog has no code to create.

**All of that is the pipeline's job.** `studio-prod.yaml`'s `smoke` job runs
[`../scripts/prod-seed-smoke.py`](../scripts/prod-seed-smoke.py) against
[`../seeds/smoke.json`](../seeds/smoke.json) before the suite: it creates the
account if absent, sets its password, and creates the library, its root node and
the one membership row if absent — idempotently, every deploy. A pool or a table
recreated tomorrow is restored by the next run rather than found a week later as
a mystery failure.

What is left for a human is the one thing CI cannot grant itself: **a password.**

## What it also proves: the provider credential

**The deployed function holds a secret** — a `SecureString` at `/studio/prod/replicate-api-token`,
read at call time under the Lambda's own role rather than injected as an
environment variable. That is a new IAM grant, and a new IAM grant is the one
class of failure this suite exists for: moto does not enforce IAM and the
integration suite runs under a developer's much wider key, so neither can tell
you whether the *deployed role* may make the call.

`test_the_lambda_can_read_the_provider_token` drives
`GET /api/models/<name>/schema`, which makes the API fetch the token, decrypt it
and call Replicate — the whole credential path — **without creating a
prediction**. Proving it through a submission would mean a real generation on
every deploy: a bill, and a payload nobody approved.

**The value comes from a GitHub environment secret**, `REPLICATE_API_TOKEN` on
the `studio-production` environment:

```
Settings → Environments → studio-production → Add secret
  REPLICATE_API_TOKEN = r8_…
```

`studio-prod.yaml` writes it into the SecureString on every app deploy, so
rotating the token is: update the secret, re-run the workflow. The workflow
**skips rather than writes** when the secret is unset — an empty SecureString
would overwrite a good token with nothing and surface much later as "the provider
is down".

Terraform creates the parameter with a placeholder and carries
`ignore_changes = [value]`, so the written token survives every apply. It is
deliberately not a `TF_VAR_`: that would put the secret in the plan output and
in the state file.

Until it is set, this test fails with a message naming the four things that look
identical from outside — a missing `ssm:GetParameter`, a missing `kms:Decrypt`,
an unset parameter name, and the placeholder itself.

## This is a detector, not a gate

Say it plainly, because the shape of the workflow invites the opposite reading.
Studio has no staging environment. `studio-prod.yaml` deploys straight to
production, and the smoke job runs **after** `update-lambda` — the new image is
already serving every request by the time the suite signs in. **Nothing here
prevents a bad deploy from reaching anyone.**

It fails the workflow because red is the signal. What it buys is the difference
between a broken deploy announcing itself in minutes with a named cause and
being found weeks later by whoever opened the site — which is exactly how a
missing `dynamodb:BatchGetItem` grant was found, behind a fully green suite.

## The library it can reach, and the one it cannot

**The smoke account is a member of exactly one library, its own, and never of
any other.** That is structural rather than careful: `app_factory`'s
`before_request` resolves the library a request is about from the caller's own
membership rows, so a caller with one membership can only ever address that one,
and every route then checks the node's own `lib` against the same rows.

Three things hold it up:

1. The seeder writes that one membership and never another, and **refuses to
   finish** if it reads the account's partition back and finds a second. The
   suite never gets a token.
2. No request in the suite sends `X-Studio-Library`, the only header that could
   name a different library.
3. The suite's first assertion is that `GET /api/libraries` returns exactly the
   smoke library — and every fixture that writes depends on that check passing.

If the smoke account ever turns up in another library, that is a hand-written
row and the remedy is to delete it. The seed step reports a **count** and not
the ids it found; another library's id does not belong in a CI log.

## Before you start

- A `gh` login with write access to this repository's Actions secrets. **No AWS
  session is needed** — this step touches GitHub only.
- A password you generate yourself, meeting the pool policy: **12+ characters
  with a lower-case letter, an upper-case letter and a digit** (symbols allowed,
  not required — `../infra/modules/auth/main.tf`).

**The password goes into no file here, no commit message, no PR description.**
The repository is private and that is not the reason to be careful. The script
reads it from your environment or prompts without echo, and pipes it to `gh` on
stdin rather than as an argument, so it never lands in `ps`.

**No IAM change is needed.** The CI role already carries `cognito-idp:*` and
`dynamodb:*` on `*` (`../../infra/envs/shared/main.tf`), which is what the seeder
uses. The only resource-scoped statement in that policy is the SSM one, and
`/studio/*` is on it.

## The step

```bash
./studio/scripts/prod-github-set-secrets.sh          # prompts, without echo
```

One secret, **`SMOKE_TEST_USER_PASSWORD`**, on the **`studio-production`
environment** of `ansavva/andreas-services`.

**Why the environment and not the repository:** a repository secret is visible
to every workflow in the repo; an environment secret is visible only to a job
that declares `environment: studio-production`. The flip side is the trap worth
recognising on sight — a job that forgets that key, or borrows another
environment's name, sees the secret as an **empty string, silently**. The seed
step and the suite both fail fast naming the variable rather than trying to sign
in as nobody, and the first thing to check when they do is `environment:`.

Re-running rotates it, and the next deploy resets the account to the new value —
so a rotation converges rather than locking the suite out.

### Verify without changing anything

```bash
./studio/scripts/prod-github-set-secrets.sh --check
```

## Then: prove it end to end

Merge to `main`, or dispatch **Studio · Deploy · Prod**, and watch the `smoke`
job. The seed step runs before pytest, so a provisioning problem fails there
with a named error rather than as a mystery assertion afterwards.

Green means a real ID token from the real pool reached the deployed Lambda,
which listed a folder, signed an upload, took bytes through S3 and back, and
deleted them again — **under the function's own execution role**, which is the
one thing no test on a laptop can exercise.

## Adding another smoke identity is not in this runbook

It is an edit to [`../seeds/smoke.json`](../seeds/smoke.json) and nothing else —
no script run, no second secret. The next deploy provisions it.

Whether it should be *another library* is the question to think about first. A
second library would make cross-library isolation testable, which nothing
asserts today. It would also double the number of places this account can write,
and the reason the current shape is worth defending is that there is exactly
one.

The addresses are committed on purpose: every one ends in `.test`, a reserved
TLD (RFC 2606) that can never be a real mailbox, and nothing is mailed to them
anyway — the seeder passes `MessageAction SUPPRESS` and sets the password
itself. **A real mailbox must never appear there**, and the seeder refuses a
fixture whose address is outside `.test`.

## Done when

- `./studio/scripts/prod-github-set-secrets.sh --check` passes.
- One **Studio · Deploy · Prod** run has a green `smoke` job.
- A deploy that breaks the deployed API's IAM, its environment or its routing
  says so on the same run, instead of on a Tuesday.

## When it goes wrong

| Symptom | Cause |
|---|---|
| Seed: `refusing: fixture references ${SMOKE_TEST_USER_PASSWORD} and SMOKE_TEST_USER_PASSWORD is unset` | The secret is unset, **or** the job lost its `environment: studio-production` key — an environment-scoped secret resolves to an empty string in silence when the environment is missing or borrowed. |
| Seed: `SMOKE_TEST_USER_PASSWORD does not meet the pool's policy` | The stored value no longer satisfies 12+/upper/lower/digit. Re-run the script. |
| Seed: `REFUSING TO CONTINUE: the smoke account holds N memberships` | Somebody added the smoke account to another library by hand. Remove that row; nothing in this repository writes it. |
| Seed: `AccessDenied` on `cognito-idp:AdminCreateUser` or a DynamoDB call | The job is not running as the CI role — check `role-to-assume` and the OIDC trust. The grants themselves are `*`. |
| Seed: `already opens on a different root node` | The fixture's `library.root_node` was changed after the library was created. Repointing would strand everything under the old root; resolve by hand. |
| Suite: `Sign-in failed (NotAuthorizedException)` | Wrong password **or** no such account; the pool sets `prevent_user_existence_errors` and will not say which. If the seed step was green, suspect a rotation that only half landed. |
| Suite: `ISOLATION VIOLATED` | As above — a second membership, caught at the fixture instead of the seeder. Nothing was written. |
| Suite: `Could not read the catalog` on a listing | The API role is missing a DynamoDB action. This is the failure the whole job exists to catch; `backend/tests/unit/test_iam_agreement.py` names which calls need which grant. |
| Suite: a 401 on every call | The Lambda's `STUDIO_COGNITO_*` environment no longer matches the pool. `update-lambda` owns that map and **replaces** it wholesale — a dropped line unsets a variable. |
