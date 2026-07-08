"""Runtime configuration helpers.

Tiny env-driven accessors used across handlers, clients, repositories, and domain layers.
Kept pure (no AWS, no I/O) so it can be imported anywhere, including under tests.
"""

import os


def table_suffix():
    """Per-environment table suffix (e.g. "" for prod, "-pr-42" for previews)."""
    return os.environ.get("WEBSITE_TABLE_SUFFIX", "")


def intake_table():
    """DynamoDB table name holding intake ("scoped quote") submissions."""
    return f"website-intake{table_suffix()}"


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
