"""Caller identity, read from the API Gateway Cognito authorizer.

Every /api route except the public reader sits behind the API Gateway JWT
authorizer, so by the time a request reaches Flask the token is already
verified and its claims are on the event. Re-verifying the signature here would
duplicate what the gateway did; what this module does instead is refuse to
*guess* an identity when the claims are absent.

That refusal matters: a teacher's page list is scoped entirely by the subject
claim, so a silent fallback to some default id would hand one teacher another
teacher's pages.
"""

from flask import request


class Unauthenticated(Exception):
    """No verified Cognito identity on the request."""


def _authorizer_claims() -> dict:
    """Claims the API Gateway authorizer attached to this request.

    Mangum puts the raw Lambda event on the WSGI environ under
    ``aws.event``. Both the HTTP API (v2, ``authorizer.jwt.claims``) and the
    REST API (v1, ``authorizer.claims``) shapes are read, so this keeps working
    if the gateway type changes.
    """
    event = request.environ.get("aws.event") or {}
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    jwt_claims = (authorizer.get("jwt") or {}).get("claims")
    if isinstance(jwt_claims, dict):
        return jwt_claims
    claims = authorizer.get("claims")
    return claims if isinstance(claims, dict) else {}


def current_teacher() -> dict:
    """The authenticated teacher as ``{"id", "email", "name"}``.

    Raises ``Unauthenticated`` when the request carries no verified subject,
    which app_factory maps to a 401.
    """
    claims = _authorizer_claims()
    teacher_id = claims.get("sub")
    if not teacher_id:
        raise Unauthenticated("no verified Cognito identity on this request")
    return {
        "id": teacher_id,
        "email": claims.get("email", ""),
        "name": claims.get("name") or claims.get("cognito:username", ""),
    }
