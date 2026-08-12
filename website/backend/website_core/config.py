"""Runtime configuration helpers.

Tiny env-driven accessors used across handlers, clients, repositories, and domain layers.
Kept pure (no AWS, no I/O) so it can be imported anywhere, including under tests.
"""

import os


def intake_table():
    """DynamoDB table name holding intake ("scoped quote") submissions.

    Terraform passes the real name in; the default matches what it builds for
    prod so local dev against DynamoDB Local needs no extra configuration.
    """
    return os.environ.get("WEBSITE_INTAKE_TABLE", "website-prod-intake")


def dynamodb_endpoint_url():
    """DynamoDB endpoint override used by local dev against DynamoDB Local."""
    return os.environ.get("DYNAMODB_ENDPOINT_URL", "")


def kit_api_key():
    """Kit (ConvertKit) API key for newsletter subscribes; "" when unconfigured."""
    return os.environ.get("KIT_API_KEY", "")


def kit_form_id():
    """Kit (ConvertKit) form id newsletter subscribers are added to."""
    return os.environ.get("KIT_FORM_ID", "")


def allowed_origin():
    """Value for Access-Control-Allow-Origin. Defaults to the prod site origin;
    set WEBSITE_ALLOWED_ORIGIN to override (e.g. per PR preview)."""
    return os.environ.get("WEBSITE_ALLOWED_ORIGIN", "https://www.andreas.services")
