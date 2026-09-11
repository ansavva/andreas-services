"""Runtime configuration helpers.

Small env-driven accessors, kept pure (no AWS calls) so any module can import
them without dragging boto3 into a unit test.
"""

import os


def public_site_base() -> str:
    """Absolute public base URL of the classroom site (no trailing slash).

    Set by ``CLASSROOM_PUBLIC_SITE_URL`` per environment
    (e.g. ``https://classroom.andreas.services``). Used to build the share link
    a teacher hands to students. Returns "" when unconfigured so unit tests can
    assert on relative paths.
    """
    return os.environ.get("CLASSROOM_PUBLIC_SITE_URL", "").rstrip("/")


def dynamodb_endpoint_url() -> str:
    """DynamoDB endpoint override used by local dev against DynamoDB Local."""
    return os.environ.get("DYNAMODB_ENDPOINT_URL", "")


def allowed_origins() -> list[str]:
    """Origins the browser API accepts, from ``CLASSROOM_ALLOWED_ORIGIN``.

    Comma-separated, so a stack can allow a deployed host and a local one at
    once. Defaults to the local app rather than to ``"*"``: an unset variable
    should fail closed and be obvious, not quietly open the API to every origin.
    """
    raw = os.environ.get("CLASSROOM_ALLOWED_ORIGIN", "http://localhost:5174")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def cognito_user_pool_id() -> str:
    """The pool whose tokens this API accepts. No default, deliberately.

    A pool id that is merely WRONG rejects every caller; one naming a different
    pool would admit that pool's users. There is no value worth guessing, so an
    unset variable is a refusal rather than a fallback.
    """
    return os.environ.get("CLASSROOM_COGNITO_USER_POOL_ID", "")


def cognito_client_id() -> str:
    """The app client a token's `aud` must match. No default, as above."""
    return os.environ.get("CLASSROOM_COGNITO_CLIENT_ID", "")


def aws_region() -> str:
    """Region for the Cognito issuer URL. Lambda always sets AWS_REGION."""
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
