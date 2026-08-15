"""Runtime configuration helpers.

Tiny env-driven accessors used across handlers, clients and services. Kept pure
(no AWS, no I/O) so it can be imported anywhere, including under tests.
"""

import os


def media_bucket():
    """The S3 bucket the browser reads.

    Owned by the x-harness pipeline, not by this service — Terraform passes the
    name in but never manages the bucket itself. The default matches prod so
    local dev needs no extra configuration.
    """
    return os.environ.get("STUDIO_MEDIA_BUCKET", "xharness-prod-media-us-east-1")


def media_root_prefix():
    """The single prefix inside the bucket this service may read.

    Every key and prefix the API accepts is validated against this, so it is the
    one place the browsable surface is defined. Always ends in a slash.
    """
    value = os.environ.get("STUDIO_MEDIA_ROOT_PREFIX", "media/")
    return value if value.endswith("/") else value + "/"


def presign_ttl_seconds():
    """How long a presigned URL is requested for.

    Deliberately short. A URL signed with the Lambda role's temporary
    credentials dies when *those* expire regardless of what we ask for here, so
    a long TTL would only be a lie the frontend then has to discover. The
    frontend re-signs through `/api/asset` when a URL stops working.
    """
    return int(os.environ.get("STUDIO_PRESIGN_TTL_SECONDS", "900"))


def max_text_bytes():
    """Size cap for the read-only text/JSON viewer endpoint."""
    return int(os.environ.get("STUDIO_MAX_TEXT_BYTES", str(1024 * 1024)))


def allowed_origin():
    """Value for Access-Control-Allow-Origin. Defaults to the prod app origin."""
    return os.environ.get("STUDIO_ALLOWED_ORIGIN", "https://studio.andreas.services")


def aws_region():
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
