# /// script
# requires-python = ">=3.11"
# dependencies = ["pycognito>=2024.5.1"]
# ///
"""Mint an ID token for the smoke account, by SRP.

Run by `conftest.py`, which supplies the pool. This file is the half that cannot
be written against the AWS CLI.

**Why a dependency rather than the AWS CLI.** `aws cognito-idp` cannot do SRP —
it offers `initiate-auth` with `USER_PASSWORD_AUTH` and `admin-initiate-auth`
with `ADMIN_USER_PASSWORD_AUTH`, and the studio pool's app client enables
neither (`infra/modules/auth`: `ALLOW_USER_SRP_AUTH` and refresh, nothing else).
Reaching for one would mean widening a production pool to suit a test harness,
which is the wrong way round: the harness should exercise the flow the SPA
actually uses. `pycognito` implements SRP client-side, so this signs in against
the pool exactly as configured and proves the same path Amplify drives in a
browser.

**It can only ever sign in as the smoke account.** The address is read from
`seeds/smoke.json` and is not an input — there is no variable, and no flag, that
would point this at a person's account. That matters because studio has no
supported way to hold a production token and should not grow one by accident:
what this mints belongs to an identity that is a member of exactly one library,
and that library holds nothing but what a smoke run put there.

**The token goes to stdout and nothing else does.** Every diagnostic is on
stderr. The password arrives in the environment, is never printed, never logged,
and never put in argv — an argument is readable in `ps` by every other process
on the machine for as long as the call takes.

**The Cognito client is UNSIGNED, and that is load-bearing.** `InitiateAuth` is
an unauthenticated API — signing in is what a user without AWS access does — but
boto3 resolves the credential chain when the client is *constructed*, before any
of that matters. `signature_version=UNSIGNED` makes botocore skip credential
resolution entirely, so this works with no AWS credentials at all, which is the
right contract for a harness that holds a pool id and a password and has no
reason to hold anything else.
"""

import json
import os
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[3] / "seeds" / "smoke.json"


def main() -> int:
    try:
        from botocore import UNSIGNED
        from botocore.config import Config
        from pycognito import Cognito
    except ImportError:  # pragma: no cover - uv resolves this before we run
        print("pycognito is not installed; run this through uv.", file=sys.stderr)
        return 1

    try:
        username = json.loads(FIXTURE.read_text())["user"]["email"]
    except (OSError, ValueError, KeyError) as error:
        print(f"Could not read the smoke identity from {FIXTURE}: {error}", file=sys.stderr)
        return 1

    try:
        pool_id = os.environ["STUDIO_SMOKE_POOL_ID"]
        client_id = os.environ["STUDIO_SMOKE_CLIENT_ID"]
        password = os.environ["SMOKE_TEST_USER_PASSWORD"]
    except KeyError as missing:
        # Names the variable, never a value.
        print(f"{missing.args[0]} is not set.", file=sys.stderr)
        return 1

    if not password.strip():
        print("SMOKE_TEST_USER_PASSWORD is empty.", file=sys.stderr)
        return 1

    region = os.environ.get("AWS_REGION") or pool_id.split("_", 1)[0]

    try:
        user = Cognito(
            pool_id,
            client_id,
            user_pool_region=region,
            username=username,
            botocore_config=Config(signature_version=UNSIGNED),
        )
        user.authenticate(password=password)
    except Exception as error:  # noqa: BLE001 - the class varies by failure mode
        # `type(error).__name__` rather than `str(error)`: botocore puts the
        # username in some messages, and this runs in logs people read.
        # NotAuthorizedException means a wrong password OR no such account,
        # because the pool sets `prevent_user_existence_errors = ENABLED` and
        # will not distinguish them — that is the pool working, not this being
        # vague.
        print(
            f"Sign-in failed ({type(error).__name__}). Wrong password, or no such "
            "account — the pool will not say which. The seed step converges both; "
            "check that it ran.",
            file=sys.stderr,
        )
        return 1

    if not user.id_token:
        print("Cognito returned no ID token.", file=sys.stderr)
        return 1
    print(user.id_token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
