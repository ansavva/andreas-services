"""Single-table data access for the classroom DynamoDB table.

One table holds every page, keyed by its owning teacher so a teacher's list is
a single query:

    PK = TEACHER#<cognito_sub>      SK = PAGE#<page_id>

**Metadata only.** A page's content is a directory of files in S3
(``repositories/lessons``); this table holds what a directory cannot — the
title, the publication state, the timestamps and the file count.

There is no secondary index, and no public read path here at all. There used to
be both: GSI1 mapped a public slug to a page so an anonymous student read was a
single query. Students no longer read through the API — they open a lesson's
files directly from CloudFront — so the index had no queries left and the slug
had no readers. Both were removed rather than maintained for nobody.
"""

import os
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

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


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




# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------

def _teacher_pk(teacher_id: str) -> str:
    return f"TEACHER#{teacher_id}"


def _page_sk(page_id: str) -> str:
    return f"PAGE#{page_id}"



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




# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def put_page(item: dict) -> dict:
    """Write a page item.

    `published` is now just a flag recording an outcome: what actually gates a
    lesson is whether its files exist under the served prefix in S3. See
    `repositories/lessons.publish`.
    """
    record = dict(item)
    record["PK"] = _teacher_pk(record["teacher_id"])
    record["SK"] = _page_sk(record["page_id"])
    record["entity_type"] = PAGE
    pages().put_item(Item=record)
    return record


def delete_page(teacher_id: str, page_id: str) -> None:
    pages().delete_item(
        Key={"PK": _teacher_pk(teacher_id), "SK": _page_sk(page_id)}
    )
