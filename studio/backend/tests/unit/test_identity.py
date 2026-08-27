"""Token verification, against tokens this test signs itself.

No network and no Cognito. A keypair is generated here, the tokens are signed
with the private half, and the JWKS lookup is stubbed to hand back the public
half — so what is under test is the four checks, not PyJWT's HTTP client. The
stub still reads the token's header the way `PyJWKClient` does, which is what
keeps the malformed case failing where it really would.
"""

import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from studio_core.errors import AuthError, ConfigError
from studio_core.services import identity

POOL_ID = "us-east-1_TESTPOOL"
CLIENT_ID = "1example23client45id"
ISSUER = f"https://cognito-idp.us-east-1.amazonaws.com/{POOL_ID}"
SUB = "11111111-2222-3333-4444-555555555555"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def pool(monkeypatch):
    """A configured pool, and the public key in place of the real JWKS fetch."""
    monkeypatch.setenv("STUDIO_COGNITO_USER_POOL_ID", POOL_ID)
    monkeypatch.setenv("STUDIO_COGNITO_CLIENT_ID", CLIENT_ID)

    class _StubKey:
        key = _KEY.public_key()

    class _StubClient:
        def get_signing_key_from_jwt(self, token):
            # `PyJWKClient` reads the header to find the `kid` before it can
            # pick a key, so a token that cannot be parsed fails here rather
            # than in `jwt.decode`. Mirrored so the malformed case exercises the
            # same branch it would in prod.
            jwt.get_unverified_header(token)
            return _StubKey()

    monkeypatch.setattr(identity, "jwks_client", _StubClient)
    identity.reset_jwks_client()
    yield
    identity.reset_jwks_client()


def _token(**overrides):
    """A Cognito-shaped ID token, valid unless a claim is overridden."""
    now = dt.datetime.now(tz=dt.timezone.utc)
    claims = {
        "sub": SUB,
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "token_use": "id",
        "email": "someone@example.com",
        "iat": now,
        "exp": now + dt.timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, _KEY, algorithm="RS256")


def _header(**overrides):
    return f"Bearer {_token(**overrides)}"


def test_valid_token_yields_the_sub():
    assert identity.caller_sub(_header()) == SUB


def test_expired_token_is_refused():
    hour_ago = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=1)
    with pytest.raises(AuthError):
        identity.caller_sub(_header(exp=hour_ago))


def test_missing_expiry_is_refused():
    """PyJWT verifies `exp` when present; the `require` list is what demands it."""
    with pytest.raises(AuthError):
        identity.caller_sub(_header(exp=None))


def test_token_for_another_client_is_refused():
    with pytest.raises(AuthError):
        identity.caller_sub(_header(aud="9someone10elses11client"))


def test_token_from_another_pool_is_refused():
    with pytest.raises(AuthError):
        identity.caller_sub(_header(iss="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_OTHER"))


def test_access_token_is_refused():
    """The check humbugg makes in reverse: studio accepts only `token_use: "id"`."""
    with pytest.raises(AuthError):
        identity.caller_sub(_header(token_use="access"))


def test_token_signed_by_someone_else_is_refused():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {
        "sub": SUB,
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "token_use": "id",
        "exp": dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(hours=1),
    }
    forged = jwt.encode(claims, other, algorithm="RS256")
    with pytest.raises(AuthError):
        identity.caller_sub(f"Bearer {forged}")


def test_malformed_token_is_refused():
    with pytest.raises(AuthError):
        identity.caller_sub("Bearer not.a.token")


@pytest.mark.parametrize("header", [None, "", "   ", "Bearer", "Bearer ", "Basic abc123"])
def test_a_header_that_is_not_a_bearer_token_is_refused(header):
    with pytest.raises(AuthError):
        identity.caller_sub(header)


def test_an_unconfigured_pool_is_a_config_error_not_an_auth_error(monkeypatch):
    """A 500, deliberately: the deployment is broken, the caller is not."""
    monkeypatch.setenv("STUDIO_COGNITO_USER_POOL_ID", "")
    with pytest.raises(ConfigError):
        identity.caller_sub(_header())


def test_the_error_never_carries_the_token():
    header = _header(token_use="access")
    with pytest.raises(AuthError) as raised:
        identity.caller_sub(header)
    assert header.removeprefix("Bearer ") not in str(raised.value)


def test_the_error_handler_answers_401():
    """`AuthError` is wired to a 401 in the app factory, not a 400 or a 500."""
    from studio_core.app_factory import create_app

    app = create_app()

    @app.get("/api/_auth_probe")
    def _probe():
        raise AuthError("The token is not valid.")

    resp = app.test_client().get("/api/_auth_probe")
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "The token is not valid."}
