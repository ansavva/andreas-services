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
