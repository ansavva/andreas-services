"""Who the caller is, taken from the Cognito ID token on the request.

One question first, because it is the one every reader arrives with: **the API
sits behind an API Gateway Cognito authorizer that has already validated this
token, so why validate it again here instead of reading
`requestContext.authorizer.claims`?** Two independent reasons, both verified
rather than assumed:

* **Those claims cannot reach Flask.** `asgiref.wsgi.WsgiToAsgi.build_environ`
  assembles the WSGI environ from a fixed list of keys, so Mangum's `aws.event`
  scope extension — the only place the authorizer's claims live — is dropped
  before Flask ever sees the request. Nor can the claim be lifted into a header
  at the gateway instead: an `AWS_PROXY` integration ignores
  `requestParameters`. This is the same seam that `BodyLengthMiddleware`
  already works around in `app_factory`, from the other side.
* **`dev-up.sh` has no authorizer at all**, and dev will be a different pool
  from prod. In-app validation is the only mechanism that behaves identically
  on a laptop, in dev and in prod, which is what stops "works locally" from
  meaning nothing about identity.

The authorizer **stays** regardless. It is the outer gate that keeps unsigned
traffic off the Lambda entirely, and it carries the CORS gateway responses that
are what make a 401 legible to the SPA rather than an opaque network error.

**The ID token, not the access token.** That is what the frontend sends and what
the authorizer checks (see `frontend/src/apis/client.ts`), and `sub` is on it
identically. So the four checks below mirror humbugg's `OnTokenValidated`
(`humbugg/backend/Humbugg.Api/Program.cs`) with the one substitution that
follows from the token kind: humbugg validates an access token and so checks
`token_use == "access"` and `client_id`, while the same facts on an ID token are
`token_use == "id"` and `aud`. Issuer and expiry are unchanged. Humbugg is the
reference implementation in this repo; this is that pattern in Python.
"""

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from studio_core import config
from studio_core.errors import AuthError, ConfigError, UpstreamError

# Cognito signs with RS256 and nothing else. Passing the list explicitly is what
# refuses a token whose own header asks to be verified with `none` or with a
# symmetric algorithm keyed on the public key.
ALGORITHMS = ["RS256"]

_jwks_client = None


def jwks_client() -> PyJWKClient:
    """Lazily built, module-cached client over the pool's JWKS endpoint.

    Cached because a Lambda execution environment serves many requests and the
    key set changes about never; `PyJWKClient` additionally holds the fetched
    set for its own lifespan, so a warm container verifies without a network
    call and a cold one pays for exactly one. The fetch has internet: this
    Lambda is not in a VPC.
    """
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"{_issuer()}/.well-known/jwks.json")
    return _jwks_client


def reset_jwks_client() -> None:
    """Drop the cached client. Tests use this; nothing in the service does."""
    global _jwks_client
    _jwks_client = None


def caller_sub(authorization_header: str | None) -> str:
    """The Cognito `sub` of the caller, or `AuthError` if there is no valid one.

    `sub` and not the email address: it is the pool's immutable identifier for a
    user, while an email can be changed. Anything that records ownership records
    this.
    """
    token = _bearer_token(authorization_header)
    client_id = config.cognito_client_id()
    if not client_id:
        raise ConfigError("STUDIO_COGNITO_CLIENT_ID is not set.")

    try:
        signing_key = jwks_client().get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError as error:
        # The pool's keys being unreachable says nothing about the caller, so
        # this is a 502 and not a 401: telling a signed-in user to sign in again
        # would send them round a loop that cannot help.
        raise UpstreamError("Could not reach the Cognito key set.") from error
    except (PyJWKClientError, InvalidTokenError) as error:
        # An unknown `kid`, or a token too malformed to read a header from.
        raise AuthError("The token is not valid.") from error

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=client_id,
            issuer=_issuer(),
            # Signature, `aud`, `iss` and `exp` are all verified by default; the
            # requirement list is what turns a *missing* claim from a silent
            # pass into a rejection, which matters most for `exp`.
            options={"require": ["exp", "iss", "aud", "sub", "token_use"]},
        )
    except InvalidTokenError as error:
        raise AuthError("The token is not valid.") from error

    # Last of the four, and the only one PyJWT has no opinion about. Without it
    # an access token from the same pool and client would sail through — it
    # carries neither `aud` nor `token_use: "id"`, so in practice it fails the
    # audience check first, but that is a coincidence of Cognito's token shapes
    # rather than a decision this code made.
    if claims["token_use"] != "id":
        raise AuthError("The token is not valid.")

    return claims["sub"]


def _bearer_token(authorization_header: str | None) -> str:
    """The credential out of an `Authorization: Bearer <token>` header."""
    if not authorization_header:
        raise AuthError("An Authorization header is required.")

    scheme, _, credential = authorization_header.partition(" ")
    credential = credential.strip()
    if scheme.lower() != "bearer" or not credential:
        raise AuthError("The Authorization header must carry a bearer token.")
    return credential


def _issuer() -> str:
    """The pool's issuer URL — both the `iss` to expect and the JWKS host."""
    pool_id = config.cognito_user_pool_id()
    if not pool_id:
        raise ConfigError("STUDIO_COGNITO_USER_POOL_ID is not set.")
    return f"https://cognito-idp.{config.aws_region()}.amazonaws.com/{pool_id}"
