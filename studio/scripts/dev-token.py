# /// script
# requires-python = ">=3.11"
# dependencies = ["pycognito>=2024.5.1"]
# ///
"""Mint an ID token for the dev pool's test account, by SRP.

Run through `dev-token.sh`, which locates the pool and loads the password. This
file is the half that cannot be written in bash.

**Why a dependency rather than the AWS CLI.** `aws cognito-idp` cannot do SRP —
it offers `initiate-auth` with `USER_PASSWORD_AUTH` and `admin-initiate-auth`
with `ADMIN_USER_PASSWORD_AUTH`, and *both* need an explicit auth flow enabled on
the app client that studio's pools deliberately do not carry. Reaching for one
would mean widening the pool to suit the test harness, which is the wrong way
round: the harness should exercise the flow the SPA actually uses. `pycognito`
implements SRP client-side, so this works against the pool exactly as configured
and proves the same code path Amplify drives in the browser.

**The token goes to stdout and nothing else does.** Every diagnostic is on
stderr, so `--header "Authorization: Bearer $(dev-token.sh)"` is safe. The
password is never printed, never logged, and never put in argv — it arrives in
the environment, because an argument is readable in `ps` by every other process
on the machine for as long as the call takes.

**The Cognito client is UNSIGNED, and that is load-bearing.** `InitiateAuth` is
an unauthenticated API — signing in is what a user without AWS access does — but
boto3 resolves the credential chain when the client is *constructed*, before any
of that matters. On a machine whose profile uses a credential provider boto3
cannot load, that turns "sign in as a Cognito user" into a traceback about
`botocore[crt]`, which is how this was found. `signature_version=UNSIGNED` makes
botocore skip credential resolution entirely, so this works with no AWS
credentials at all — which is also the right contract for a harness that has a
pool id and a password and no reason to hold anything else.
"""

import os
import sys


def main() -> int:
    try:
        from botocore import UNSIGNED
        from botocore.config import Config
        from pycognito import Cognito
    except ImportError:  # pragma: no cover - uv resolves this before we run
        print("pycognito is not installed; run this through dev-token.sh.", file=sys.stderr)
        return 1

    try:
        pool_id = os.environ["STUDIO_DEV_POOL_ID"]
        client_id = os.environ["STUDIO_DEV_CLIENT_ID"]
        username = os.environ["STUDIO_DEV_USER_EMAIL"]
        password = os.environ["STUDIO_DEV_USER_PASSWORD"]
    except KeyError as missing:
        # Names the variable, never a value — the same rule the shell half holds.
        print(f"{missing.args[0]} is not set; run this through dev-token.sh.", file=sys.stderr)
        return 1

    region = os.environ.get("AWS_REGION") or pool_id.split("_", 1)[0]
    which = os.environ.get("STUDIO_DEV_TOKEN_KIND", "id")

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
        # username in some messages, and this runs in terminals people paste
        # from. NotAuthorizedException here means a wrong password OR a
        # nonexistent account, because the pool sets
        # `prevent_user_existence_errors = ENABLED` and will not distinguish
        # them — that is the pool working, not this script being vague.
        print(
            f"Sign-in failed ({type(error).__name__}). "
            "Wrong password, or no such account — the pool will not say which. "
            "Converge the account with ./studio/scripts/dev-user.sh.",
            file=sys.stderr,
        )
        return 1

    token = user.id_token if which == "id" else user.access_token
    if not token:
        print(f"Cognito returned no {which} token.", file=sys.stderr)
        return 1
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
