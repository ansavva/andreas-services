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

from studio_pipeline import profiles

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "andreas-services"
    / "studio"
)
# Beside the machine id, deliberately: both are per-machine identity, both are
# mode 600, and a developer looking for one finds the other.
CREDENTIALS_FILE = CONFIG_DIR / "credentials"

# `DEFAULT_API_URL = "https://studio-api.andreas.services"` lived here and is
# **deleted**. It meant that a shell with nothing set — no `dev-up.sh`, no
# `.env` sourced — pointed the CLI at PRODUCTION, which is the exact opposite of
# what `studio/CLAUDE.md` says the CLI does and the same shape of default #434
# removed from `adapters/s3.py` and `adapters/ddb.py`. The target is a profile
# now, it defaults to `dev`, and "nothing is configured" is a refusal that names
# the two commands that fix it rather than a silent connection to the live
# library.


class AuthError(RuntimeError):
    """Sign-in failed, or there is no usable session."""


def api_url() -> str:
    """Where the CLI sends its calls, per the profile in force.

    An `AuthError` rather than `errors.die` when nothing supplies one, because
    `session/commands.py:_show_libraries` reports a failure here instead of
    raising: `whoami` answering "who am I" and not "what can I reach" is more
    useful than a command that exits before printing either.
    """
    resolved = profiles.value("api_url", required=False)
    if not resolved:
        raise AuthError(profiles.missing("api_url"))
    return resolved.rstrip("/")


def _pool() -> tuple[str, str, str]:
    pool_id = profiles.value("cognito_user_pool_id", required=False)
    client_id = profiles.value("cognito_client_id", required=False)
    if not pool_id or not client_id:
        raise AuthError(profiles.missing("cognito_user_pool_id"))
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


def _dump(store: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(stat.S_IRWXU)
    # Written 600 *before* the secret goes in: creating world-readable and
    # chmod-ing afterwards leaves a window, however short, where another user on
    # the machine can read a refresh token.
    fd = os.open(CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(store, handle)


def _load() -> dict:
    """Every profile's session: `{"profiles": {"<name>": {...}}}`.

    **The file used to be one flat session and that was the bug worth fixing.**
    There is one credentials file per machine, so signing in to prod overwrote
    the dev session for every shell on it, indefinitely — the target outlived
    the shell that chose it, which is precisely what a profile is supposed to
    prevent. Keyed by profile, the two coexist and neither can shadow the other.
    """
    if not CREDENTIALS_FILE.exists():
        return {"profiles": {}}
    try:
        data = json.loads(CREDENTIALS_FILE.read_text())
    except (OSError, ValueError) as error:
        raise AuthError(f"{CREDENTIALS_FILE} is unreadable. Run: studio login") from error
    if isinstance(data.get("profiles"), dict):
        return data
    return {"profiles": _migrated(data)}


def _migrated(flat: dict) -> dict:
    """Move a pre-profile session under the profile whose pool minted it.

    Read-time and in memory; it is persisted by the next `_write`. Filing it by
    the token's own `iss` rather than by whichever profile happens to be current
    is what stops a first-ever `--profile prod` invocation from inheriting a dev
    session and reporting itself signed in to production.
    """
    token = flat.get("id_token")
    if not token:
        return {}
    try:
        pool = claims(token).get("iss", "").rsplit("/", 1)[-1]
    except Exception:  # noqa: BLE001 - a stored token is not a thing to trust
        # **Every failure mode, not the two that came to mind.** `claims` splits
        # on "." and indexes [1], so a truncated or hand-edited file raises
        # IndexError — which was not in the original tuple, and turned `studio
        # logout` (the command whose whole job is getting rid of a bad session)
        # into a traceback. Unfilable is not fatal: it falls through to the
        # profile in force, which is where a session with no readable issuer
        # belongs.
        pool = ""
    for name in profiles.names():
        if pool and profiles.fields(name).get("cognito_user_pool_id") == pool:
            return {name: flat}
    return {profiles.current(): flat}


def sessions() -> set[str]:
    """Which profiles have a stored session. For `studio profile list`."""
    try:
        return set(_load()["profiles"])
    except AuthError:
        return set()


def _write(tokens: dict) -> None:
    store = _load()
    store["profiles"][profiles.current()] = tokens
    _dump(store)


def _read() -> dict:
    name = profiles.current()
    stored = _load()["profiles"].get(name)
    if not stored:
        raise AuthError(f"Not signed in on profile {name!r}. Run: studio --profile {name} login")
    return stored


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
    """Forget this profile's session. True if there was one.

    **This profile's, not every profile's.** Signing out of prod must not sign
    you out of dev — that would put back the coupling `_load` exists to remove.
    The file goes when the last session in it does, so a machine that has signed
    out of everything is left as it started.
    """
    store = _load()
    if store["profiles"].pop(profiles.current(), None) is None:
        return False
    if store["profiles"]:
        _dump(store)
    else:
        CREDENTIALS_FILE.unlink(missing_ok=True)
    return True


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
    # `api_url` is resolved defensively: an unconfigured profile is exactly when
    # someone runs `whoami`, and a stored token still answers the other four
    # lines. Same reasoning as `_show_libraries` swallowing its own failure.
    try:
        where = api_url()
    except AuthError:
        where = "(unset)"
    return {
        "profile": profiles.current(),
        "email": body.get("email") or stored.get("username", ""),
        "sub": body.get("sub", ""),
        "pool": body.get("iss", "").rsplit("/", 1)[-1],
        "expires_at": body.get("exp"),
        "api_url": where,
    }
