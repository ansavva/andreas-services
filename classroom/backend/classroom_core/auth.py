"""Who the caller is, taken from the Cognito ID token on the request.

One question first, because it is the one every reader arrives with: **the API
sits behind an API Gateway Cognito authorizer that has already validated this
token, so why validate it again here instead of reading
`requestContext.authorizer.claims`?**

This service tried that, and it did not work in production for a single day.
Two independent reasons, both measured rather than assumed:

* **Those claims cannot reach Flask.** `asgiref.wsgi.WsgiToAsgi.build_environ`
  assembles the WSGI environ from a fixed list of keys — `PATH_INFO`,
  `REQUEST_METHOD`, the `wsgi.*` set — so Mangum's `aws.event` scope extension,
  the only place the authorizer's claims live, is dropped before Flask sees the
  request. Every authenticated request answered 401. It stayed hidden because
  the production frontend deploy had never succeeded, so no signed-in request
  was ever made against prod.

* **`dev-up.sh` has no authorizer at all**, and dev is a different pool from
  prod. In-app validation is the only mechanism that behaves identically on a
  laptop, in dev and in prod — which is what stops "works locally" from meaning
  nothing about identity. The previous arrangement had the local dev server
  *fake* the claims, so local passed while prod was broken. That divergence is
  the bug, not a detail of it.

The authorizer **stays** regardless. It is the outer gate that keeps unsigned
traffic off the Lambda entirely, and it carries the CORS gateway responses that
make a 401 legible to the SPA rather than an opaque network error.

This is studio's `services/identity.py` in classroom's shape; humbugg's
`OnTokenValidated` is the reference implementation both follow.
"""

import jwt
from flask import request
from jwt import PyJWKClient
from jwt.exceptions import (
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from classroom_core import config

# Cognito signs with RS256 and nothing else. Passing the list explicitly is what
# refuses a token whose own header asks to be verified with `none` or with a
# symmetric algorithm keyed on the public key.
ALGORITHMS = ["RS256"]

_jwks_client = None


class Unauthenticated(Exception):
    """No valid Cognito identity on the request. app_factory maps this to 401."""


class AuthUnavailable(Exception):
    """The pool's keys could not be reached. Mapped to 502, deliberately not 401.

    Telling a signed-in teacher to sign in again, because *our* dependency is
    unreachable, sends her round a loop that cannot help.
    """


def jwks_client() -> PyJWKClient:
    """Lazily built, module-cached client over the pool's JWKS endpoint.

    Cached because a Lambda execution environment serves many requests and the
    key set changes about never, so a warm container verifies with no network
    call and a cold one pays for exactly one.
    """
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"{_issuer()}/.well-known/jwks.json")
    return _jwks_client


def reset_jwks_client() -> None:
    """Drop the cached client. Tests use this; nothing in the service does."""
    global _jwks_client
    _jwks_client = None


def _issuer() -> str:
    """The pool's issuer URL — both the `iss` to expect and the JWKS host."""
    pool_id = config.cognito_user_pool_id()
    if not pool_id:
        raise Unauthenticated("CLASSROOM_COGNITO_USER_POOL_ID is not set.")
    return f"https://cognito-idp.{config.aws_region()}.amazonaws.com/{pool_id}"


def _token_from_header() -> str:
    """The credential out of the Authorization header.

    Accepts a bare token as well as `Bearer <token>`: the SPA sends the raw ID
    token (see `frontend/src/api.ts`) and a person using curl types `Bearer`.
    Both are the same credential and rejecting one would be pedantry.
    """
    header = (request.headers.get("Authorization") or "").strip()
    if not header:
        raise Unauthenticated("An Authorization header is required.")

    scheme, _, credential = header.partition(" ")
    if not credential:
        return header  # a bare token, no scheme
    if scheme.lower() != "bearer":
        raise Unauthenticated("The Authorization header must carry a bearer token.")
    return credential.strip()


def verify_id_token(token: str) -> dict:
    """Validated claims from a Cognito ID token, or raise."""
    client_id = config.cognito_client_id()
    if not client_id:
        raise Unauthenticated("CLASSROOM_COGNITO_CLIENT_ID is not set.")

    try:
        signing_key = jwks_client().get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError as error:
        raise AuthUnavailable("Could not reach the Cognito key set.") from error
    except (PyJWKClientError, InvalidTokenError) as error:
        # An unknown `kid`, or a token too malformed to read a header from.
        raise Unauthenticated("The token is not valid.") from error

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=client_id,
            issuer=_issuer(),
            # Signature, `aud`, `iss` and `exp` are verified by default; the
            # requirement list is what turns a *missing* claim from a silent
            # pass into a rejection, which matters most for `exp`.
            options={"require": ["exp", "iss", "aud", "sub", "token_use"]},
        )
    except InvalidTokenError as error:
        raise Unauthenticated("The token is not valid.") from error

    # The only one PyJWT has no opinion about. Without it an access token from
    # the same pool would sail through — in practice it fails the audience check
    # first, but that is a coincidence of Cognito's token shapes rather than a
    # decision this code made.
    if claims["token_use"] != "id":
        raise Unauthenticated("The token is not valid.")

    return claims


def current_teacher() -> dict:
    """The authenticated teacher as ``{"id", "email", "name"}``.

    `sub` and not the email address: it is the pool's immutable identifier for a
    user, while an email can be changed. Every page records ownership with this.
    """
    claims = verify_id_token(_token_from_header())
    return {
        "id": claims["sub"],
        "email": claims.get("email", ""),
        "name": claims.get("name") or claims.get("cognito:username", ""),
    }
