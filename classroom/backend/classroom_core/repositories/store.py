"""Single-table data access for the classroom DynamoDB table.

One table holds every page, keyed by its owning teacher so a teacher's list is
a single query:

    PK = TEACHER#<cognito_sub>      SK = PAGE#<page_id>

GSI1 indexes the public slug so an anonymous student read is also a single
query rather than a scan:

    GSI1PK = SLUG#<slug>           GSI1SK = PAGE

Those GSI1 attributes are written only while a page is published. Unpublishing
REMOVEs them, so an unpublished page falls out of the public lookup path with
no filter expression and no risk of a stale read serving withdrawn material to
students. Publishing re-adds them.
"""

import os
import re
import secrets
import time
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from classroom_core.repositories import dynamodb


def _required_env(name: str) -> str:
    """Resolve a resource name from the environment, or fail loudly.

    Deliberately no default: a plausible-looking fallback turns a missing env
    var into silent reads and writes against the wrong table, while an
    exception at import time surfaces the misconfiguration immediately.
    """
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Terraform sets it on the Lambda; "
            "local runs and tests must set it explicitly."
        )
    return value


PAGES_TABLE = _required_env("CLASSROOM_PAGES_TABLE")

PAGE = "page"

# GSI1 attributes are present only on a published page — see module docstring.
PUBLIC_INDEX_ATTRS = ("GSI1PK", "GSI1SK")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SLUG_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"


def pages():
    return dynamodb.table(PAGES_TABLE)


def ensure_local_table_exists():
    dynamodb.ensure_local_table_exists(PAGES_TABLE)


# ---------------------------------------------------------------------------
# Identifiers & timestamps
# ---------------------------------------------------------------------------

def new_id() -> str:
    """A 26-char ULID in Crockford base32 — lexicographically sortable by
    creation time, so SKs embedding an id order chronologically."""
    ts = int(time.time() * 1000)
    ts_chars = ""
    for _ in range(10):
        ts_chars = _CROCKFORD[ts & 31] + ts_chars
        ts >>= 5
    rand_chars = "".join(secrets.choice(_CROCKFORD) for _ in range(16))
    return ts_chars + rand_chars


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(title: str) -> str:
    """A URL-safe slug from a page title, with a short random suffix.

    The suffix keeps two pages called "Warm Up" from colliding across teachers
    without making the teacher think about uniqueness. It is deliberately drawn
    from an alphabet with no look-alike characters, because these links get
    written on a whiteboard and typed by hand.
    """
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:48]
    suffix = "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(6))
    return f"{base}-{suffix}" if base else suffix


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------

def _teacher_pk(teacher_id: str) -> str:
    return f"TEACHER#{teacher_id}"


def _page_sk(page_id: str) -> str:
    return f"PAGE#{page_id}"


def _slug_pk(slug: str) -> str:
    return f"SLUG#{slug}"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_pages_for_teacher(teacher_id: str) -> list[dict]:
    """Every page owned by a teacher, newest first."""
    response = pages().query(
        KeyConditionExpression=(
            Key("PK").eq(_teacher_pk(teacher_id)) & Key("SK").begins_with("PAGE#")
        ),
        ScanIndexForward=False,
    )
    return response.get("Items", [])


def get_page(teacher_id: str, page_id: str) -> dict | None:
    response = pages().get_item(
        Key={"PK": _teacher_pk(teacher_id), "SK": _page_sk(page_id)}
    )
    return response.get("Item")


def get_published_page_by_slug(slug: str) -> dict | None:
    """Look a published page up by its public slug.

    Unpublished pages carry no GSI1 attributes, so they are simply absent from
    this index — there is no published flag to check here, and no way for an
    unpublished page to leak through.
    """
    response = pages().query(
        IndexName="GSI1",
        KeyConditionExpression=(
            Key("GSI1PK").eq(_slug_pk(slug)) & Key("GSI1SK").eq("PAGE")
        ),
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def put_page(item: dict) -> dict:
    """Write a page item, adding or stripping the public index in step with
    its published flag."""
    record = dict(item)
    record["PK"] = _teacher_pk(record["teacher_id"])
    record["SK"] = _page_sk(record["page_id"])
    record["entity_type"] = PAGE

    if record.get("published"):
        record["GSI1PK"] = _slug_pk(record["slug"])
        record["GSI1SK"] = "PAGE"
    else:
        for attr in PUBLIC_INDEX_ATTRS:
            record.pop(attr, None)

    pages().put_item(Item=record)
    return record


def delete_page(teacher_id: str, page_id: str) -> None:
    pages().delete_item(
        Key={"PK": _teacher_pk(teacher_id), "SK": _page_sk(page_id)}
    )
