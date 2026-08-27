"""The CLI against a real dev stack. Opt-in, and silent otherwise.

**This tier did not exist.** Every other test of the CLI talks to
`tests/support/fake_api.py`, and nothing had ever proved the real Flask API
answers the way that fake claims — which is the same class of gap that let a
missing `dynamodb:BatchGetItem` grant reach production, because moto enforces no
IAM either. A seeded dev stack is what made it possible to close.

Without `STUDIO_INTEGRATION=1` every test here is skipped at collection. That is
not politeness: these write to a real AWS account.

**These never run in CI.** `studio-pr.yml` validates only and never writes to
AWS; that is a repo-wide rule and this does not become the exception. The gate is
local, and `scripts/dev-test-integration.sh` is the runner.

WHY EVERY TEST SHELLS OUT
-------------------------
`tests/conftest.py` — the parent of this directory — pins `STUDIO_S3_BUCKET` and
`STUDIO_CATALOG_TABLE` to PRODUCTION names at import time, points AWS at fake
credentials, starts moto, and autouses five fixtures that redirect the profile
directory, the stored session and the model registry. All of that is right for a
unit suite and all of it is wrong here.

Overriding it in-process would mean unpicking five fixtures and two module-level
assignments that have already run. Running the real `studio` binary in a
subprocess sidesteps every one of them, and it is also what a developer actually
types — so a break in the entry point is a failure here rather than a surprise
later. `conftest.py` builds that subprocess's environment explicitly rather than
inheriting this one; read `studio_env` before adding a test.
"""
