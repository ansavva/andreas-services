# The catalog table's client, plus the item marshalling every caller needs.
#
# Credentials come from `s3.py`. boto3's default chain does not understand the
# AWS CLI's `aws login` session and that module already bridges it, so this one
# asks it for a session rather than solving the same problem a second time —
# the bridge resolves a *session*, not an S3 session.
#
# Nothing here knows what a node or a library is. That is `maintenance/
# catalog_seed.py`'s subject; this is the outside world, in `adapters/`.
from __future__ import annotations

import os

from studio_pipeline.adapters import s3 as s3c

# `[project]-[env]-[component]`, the monorepo's naming convention. Studio has
# exactly one environment and local runs against it (see studio/CLAUDE.md), so
# `prod` here is the real table and not a placeholder for a dev copy that does
# not exist. Overridable for the same reason `STUDIO_S3_BUCKET` is.
TABLE = os.environ.get("STUDIO_CATALOG_TABLE", "studio-prod-catalog")


def client():
    """A boto3 DynamoDB client authenticated exactly as the S3 one is."""
    return s3c.session().client("dynamodb")


# ── marshalling ─────────────────────────────────────────────────────────────
#
# The document API (`boto3.resource`) marshals for you but has no
# `transact_write_items`, and every catalog write is a transaction because a
# node is two items. So the low-level client it is, and the typed attribute
# maps it takes are built here rather than by hand at each call site —
# `{"S": …}` / `{"N": …}` spelled out inline is where a `size` silently becomes
# a string.


def to_item(doc: dict) -> dict:
    """A plain dict -> DynamoDB's typed attribute map.

    `None` values are dropped rather than written as NULL: a folder has no
    `blob_key`, and "the attribute is absent" is what the schema means by that.
    An absent attribute is also what `attribute_not_exists` tests, so writing
    NULLs would quietly defeat the uniqueness conditions below.
    """
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    return {k: serializer.serialize(v) for k, v in doc.items() if v is not None}


def from_item(item: dict) -> dict:
    """The inverse, with numbers as ints.

    The deserializer returns `Decimal` for every N, which compares equal to an
    int but formats as `Decimal('12')` in a report and is not JSON-serialisable
    — and this command's whole output is a journal file.
    """
    import decimal

    from boto3.dynamodb.types import TypeDeserializer

    deserializer = TypeDeserializer()
    out = {}
    for key, value in item.items():
        got = deserializer.deserialize(value)
        if isinstance(got, decimal.Decimal):
            got = int(got) if got == got.to_integral_value() else float(got)
        out[key] = got
    return out


def put(doc: dict, *, unique: bool = True) -> dict:
    """One `Put` action for `transact`.

    `unique=True` attaches `attribute_not_exists(pk)`, which makes a re-run
    refuse to overwrite rather than silently reseed a library someone has since
    renamed things in. It is the condition the API uses for "name already
    taken"; here it is what makes an interrupted seed resumable.
    """
    action = {"TableName": TABLE, "Item": to_item(doc)}
    if unique:
        action["ConditionExpression"] = "attribute_not_exists(pk)"
    return {"Put": action}


def transact(ddb, actions: list[dict]) -> bool:
    """Write one atomic group. False if a uniqueness condition refused it.

    A refused condition is not an error here — it is "already seeded", the only
    way this command is resumable. Anything else (a throttle, a missing table,
    a validation failure) still raises, because those are not idempotency.
    """
    try:
        ddb.transact_write_items(TransactItems=actions)
    except ddb.exceptions.TransactionCanceledException as exc:
        reasons = {r.get("Code") for r in
                   exc.response.get("CancellationReasons", [])}
        if reasons <= {"None", "ConditionalCheckFailed"}:
            return False
        raise
    return True


def scan(ddb, **kwargs):
    """Every item in the table, paginated.

    A scan rather than a GSI query on purpose. The indexes are the API's read
    path and belong to it; a maintenance sweep wants every row that exists,
    including one a GSI dropped because a key attribute is missing — which is
    precisely the corruption `verify` is looking for.
    """
    paginator = ddb.get_paginator("scan")
    for page in paginator.paginate(TableName=TABLE, **kwargs):
        for item in page.get("Items", []):
            yield from_item(item)


def table_exists(ddb) -> bool:
    try:
        ddb.describe_table(TableName=TABLE)
    except ddb.exceptions.ResourceNotFoundException:
        return False
    return True
