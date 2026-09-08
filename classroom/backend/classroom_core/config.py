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
