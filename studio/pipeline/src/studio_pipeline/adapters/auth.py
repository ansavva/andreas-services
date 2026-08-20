"""Cognito sign-in for the CLI, holding no AWS credentials (#300).

**The point of this module is what it does *not* need.** Until now the pipeline
reached S3 directly under the developer's own AWS login, so it only ran where
credentials were configured. After this it signs in to Cognito as a user and
calls the studio API, exactly as the SPA does — a laptop with no AWS account can
drive the service.

**SRP, because the pool allows nothing else.** `explicit_auth_flows` is
`ALLOW_USER_SRP_AUTH` and `ALLOW_REFRESH_TOKEN_AUTH`; there is no
`USER_PASSWORD_AUTH` and no hosted UI. `pycognito` implements the SRP handshake
client-side, so this drives the same flow Amplify drives in the browser.

**The Cognito client is UNSIGNED, and that is load-bearing rather than tidy.**
`InitiateAuth` is an unauthenticated API — signing in is what a user without AWS
access does — but boto3 resolves the credential chain when the client is
*constructed*. Without this, `studio login` on a machine with no AWS credentials
fails inside boto3 before it ever reaches Cognito, which is precisely the machine
#300 names as the acceptance test.

**The API takes the ID token, not the access token.** A REST
`COGNITO_USER_POOLS` authorizer with no `authorization_scopes` validates an
*identity* token. Send an access token and sign-in succeeds while every call
401s — a failure that looks like a broken login and is not.

**Nothing here logs, prints or returns a token by accident.** `whoami` reports
claims; errors name the variable or the step, never the credential.
"""

from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "andreas-services"
    / "studio"
)
# Beside the machine id, deliberately: both are per-machine identity, both are
# mode 600, and a developer looking for one finds the other.
CREDENTIALS_FILE = CONFIG_DIR / "credentials"

DEFAULT_API_URL = "https://studio-api.andreas.services"


class AuthError(RuntimeError):
    """Sign-in failed, or there is no usable session."""


def api_url() -> str:
    """Where the CLI sends its calls.

    `dev-up.sh` points this at `http://localhost:8000`, which is how the CLI
    drives a locally-running API against this machine's dev stack.
    """
    return os.environ.get("STUDIO_API_URL", DEFAULT_API_URL).rstrip("/")


def _pool() -> tuple[str, str, str]:
    pool_id = os.environ.get("STUDIO_COGNITO_USER_POOL_ID", "")
    client_id = os.environ.get("STUDIO_COGNITO_CLIENT_ID", "")
    if not pool_id or not client_id:
        raise AuthError(
            "STUDIO_COGNITO_USER_POOL_ID and STUDIO_COGNITO_CLIENT_ID are not set. "
            "Run studio/scripts/dev-setup.sh, which writes them from this machine's "
            "dev stack."
        )
    region = os.environ.get("AWS_REGION") or pool_id.split("_", 1)[0]
    return pool_id, client_id, region


def _cognito(username: str | None = None):
    """A Cognito client that resolves no AWS credentials. See the module docstring."""
    from botocore import UNSIGNED
    from botocore.config import Config
    from pycognito import Cognito

    pool_id, client_id, region = _pool()
    return Cognito(
        pool_id,
        client_id,
        user_pool_region=region,
        username=username,
        botocore_config=Config(signature_version=UNSIGNED),
    )


def claims(token: str) -> dict:
    """The payload of a JWT, without verifying it.

    **Unverified on purpose, and only ever used for display.** The CLI is not an
    authority on whether a token is good — the API is, and it verifies the
    signature on every call. Decoding here is how `whoami` prints an email
    without a round trip; nothing is authorised on the result.
    """
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _write(tokens: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(stat.S_IRWXU)
    # Written 600 *before* the secret goes in: creating world-readable and
    # chmod-ing afterwards leaves a window, however short, where another user on
    # the machine can read a refresh token.
    fd = os.open(CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(tokens, handle)


def _read() -> dict:
    if not CREDENTIALS_FILE.exists():
        raise AuthError("Not signed in. Run: studio login")
    try:
        return json.loads(CREDENTIALS_FILE.read_text())
    except (OSError, ValueError) as error:
        raise AuthError(f"{CREDENTIALS_FILE} is unreadable. Run: studio login") from error


def login(username: str, password: str) -> dict:
    """Sign in by SRP and store the session. Returns the ID token's claims."""
    user = _cognito(username)
    try:
        user.authenticate(password=password)
    except Exception as error:  # noqa: BLE001 - the class varies by failure mode
        # The class name, never `str(error)`: botocore puts the username in some
        # messages and this runs in terminals people paste from.
        # `NotAuthorizedException` covers a wrong password *and* a nonexistent
        # account, because the pool sets `prevent_user_existence_errors` — that
        # is the pool working, not this being vague.
        raise AuthError(
            f"Sign-in failed ({type(error).__name__}). "
            "Wrong password, or no such account — the pool will not say which."
        ) from error

    if not user.id_token:
        raise AuthError("Cognito returned no ID token.")
    _write(
        {
            "id_token": user.id_token,
            "refresh_token": user.refresh_token,
            "username": username,
        }
    )
    return claims(user.id_token)


def logout() -> bool:
    """Forget the stored session. True if there was one."""
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
        return True
    return False


def id_token(*, refresh: bool = False) -> str:
    """The current ID token, refreshing it when asked.

    `refresh=True` is what `adapters/api.py` passes after a 401 — the CLI does
    not try to predict expiry from `exp`, because a clock that disagrees with
    Cognito's would either refresh constantly or not at all. The API's 401 is the
    authority on whether a token still works.
    """
    stored = _read()
    if not refresh:
        token = stored.get("id_token")
        if token:
            return token

    refresh_token = stored.get("refresh_token")
    if not refresh_token:
        raise AuthError("No refresh token stored. Run: studio login")

    user = _cognito(stored.get("username"))
    user.refresh_token = refresh_token
    try:
        user.renew_access_token()
    except Exception as error:  # noqa: BLE001
        raise AuthError(
            f"Could not refresh the session ({type(error).__name__}). Run: studio login"
        ) from error
    if not user.id_token:
        raise AuthError("Cognito returned no ID token on refresh. Run: studio login")

    stored["id_token"] = user.id_token
    _write(stored)
    return user.id_token


def whoami() -> dict:
    """Who the stored session belongs to, from the token's own claims."""
    stored = _read()
    token = stored.get("id_token")
    if not token:
        raise AuthError("No ID token stored. Run: studio login")
    body = claims(token)
    return {
        "email": body.get("email") or stored.get("username", ""),
        "sub": body.get("sub", ""),
        "pool": body.get("iss", "").rsplit("/", 1)[-1],
        "expires_at": body.get("exp"),
        "api_url": api_url(),
    }
