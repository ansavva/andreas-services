"""Data-access layer for the website-intake DynamoDB table.

The table holds "scoped quote" intake submissions. Every row shares a single
partition (`INTAKE`) with a time-ordered sort key, so the admin console can
list submissions newest-first with a cheap `Query` (no `Scan`) and cursor
pagination. Volume is tiny, so a single partition is fine.

Intentionally self-contained (no shared package) so it can be copied into the
Lambda image, matching the Scout convention.
"""

import base64
import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

from website_core.common import config

# All submissions live under one partition; the SK sorts by recency.
PARTITION = "INTAKE"

_dynamodb = None


def _region():
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def _table():
    """Lazy table handle so importing under moto/tests is side-effect free."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=_region())
    return _dynamodb.Table(config.intake_table())


# ---------------------------------------------------------------------------
# Cursor helpers (opaque base64 of the DynamoDB LastEvaluatedKey)
# ---------------------------------------------------------------------------

def encode_cursor(key):
    if not key:
        return None
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def decode_cursor(cursor):
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Writes / reads
# ---------------------------------------------------------------------------

def put_submission(fields):
    """Persist one intake submission and return the stored item."""
    now = datetime.now(timezone.utc).isoformat()
    submission_id = uuid.uuid4().hex
    item = {
        "PK": PARTITION,
        "SK": f"{now}#{submission_id}",
        "id": submission_id,
        "created_at": now,
        "status": "new",
        **fields,
    }
    _table().put_item(Item=item)
    return _public(item)


def list_submissions(limit=50, cursor=None):
    """Return (submissions_newest_first, next_cursor)."""
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(PARTITION),
        "ScanIndexForward": False,
        "Limit": limit,
    }
    start_key = decode_cursor(cursor)
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    resp = _table().query(**kwargs)
    items = [_public(i) for i in resp.get("Items", [])]
    return items, encode_cursor(resp.get("LastEvaluatedKey"))


def _public(item):
    """Strip internal key attributes from an item before returning it."""
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}
