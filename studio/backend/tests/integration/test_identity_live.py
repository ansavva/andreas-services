"""Token validation against a real Cognito pool (#289).

**What moto cannot cover.** The unit suite stubs `identity.caller_sub` outright,
because verifying an RS256 signature needs a live JWKS endpoint. So the one thing
never exercised anywhere is the thing every request depends on: that a token this
pool actually issued passes, and that the four ways a token can be wrong fail.
"""

import subprocess
from pathlib import Path

import pytest

from studio_core.errors import AuthError
from studio_core.services import identity

# Re-derived rather than imported from `conftest`: a relative import needs this
# directory to be a package, and making it one changes how pytest collects it.
SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_a_real_dev_pool_id_token_validates(id_token):
    """The assertion the whole dev environment exists to make possible."""
    sub = identity.caller_sub(f"Bearer {id_token}")

    assert sub and isinstance(sub, str)


def test_the_same_sub_comes_back_every_time(id_token):
    """`sub` is the pool's immutable id for the account — ownership records it."""
    assert identity.caller_sub(f"Bearer {id_token}") == identity.caller_sub(
        f"Bearer {id_token}"
    )


def test_an_access_token_from_the_same_pool_is_refused(dev_stack):
    """The check PyJWT has no opinion about.

    An access token carries the same signature, the same issuer and the same
    client — it fails only because `caller_sub` asserts `token_use == "id"`. In
    practice the audience check fires first, but that is a coincidence of
    Cognito's token shapes rather than a decision the code made, which is why
    this is asserted against a real access token rather than a hand-built one.
    """
    result = subprocess.run(  # noqa: S603
        [str(SCRIPTS / "dev-token.sh"), "--no-prompt", "--access"],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr.strip()

    with pytest.raises(AuthError):
        identity.caller_sub(f"Bearer {result.stdout.strip()}")


def test_a_token_from_another_pool_is_refused(id_token, monkeypatch):
    """Right signature, wrong issuer.

    The pool id is swapped for prod's *shape* rather than a nonsense string, so
    the failure is the issuer check rather than a malformed URL — a token minted
    by one pool must not be accepted by a service configured for another, which
    is the whole reason `_issuer()` is pinned.
    """
    monkeypatch.setenv("STUDIO_COGNITO_USER_POOL_ID", "us-east-1_hezDSsl7m")
    identity.reset_jwks_client()
    try:
        # AuthError specifically: the dev token's `kid` is not in prod's key set,
        # so `get_signing_key_from_jwt` raises `PyJWKClientError` and
        # `caller_sub` turns it into a 401. Catching bare `Exception` here would
        # let a connection failure pass as if it were a rejection.
        with pytest.raises(AuthError):
            identity.caller_sub(f"Bearer {id_token}")
    finally:
        identity.reset_jwks_client()


def test_a_malformed_token_is_refused():
    with pytest.raises(AuthError):
        identity.caller_sub("Bearer not-a-jwt")


def test_a_missing_header_is_refused():
    with pytest.raises(AuthError):
        identity.caller_sub(None)
