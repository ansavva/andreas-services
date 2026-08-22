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
from studio_pipeline.errors import die

# `[project]-[env]-[component]`, the monorepo's naming convention.
#
# **No default, and the absence is the point.** This read
# `os.environ.get("STUDIO_CATALOG_TABLE", "studio-prod-catalog")`, justified at
# the time by studio having exactly one environment that local runs addressed.
# `studio/CLAUDE.md` says the opposite now — the CLI targets a per-machine dev
# stack — so the default meant a maintenance command run in a shell that had not
# loaded `studio/.env` addressed the PRODUCTION catalog. One of the readers is
# `catalog gc`, which deletes: a dry run against the wrong table calls prod's
# blobs unreferenced, and the `--apply` that follows removes them.
#
# #434 removed exactly this default from `adapters/s3.py` and this is the same
# removal, for the reason stated there: a value that quietly points somewhere
# plausible is worse than no value. It was latent only because every command
# reading both asks `s3c.bucket()` first and dies there — call ordering, not a
# guard.
TABLE = os.environ.get("STUDIO_CATALOG_TABLE", "")


def table() -> str:
    """The catalog table, or a refusal naming what to do about it.

    Asked for through here rather than read off `TABLE`, exactly as
    `s3.bucket()` is, so "unset" cannot be discovered halfway through a
    paginate.
    """
    if not TABLE:
        die("STUDIO_CATALOG_TABLE is not set.\n"
            "       Run studio/scripts/dev-setup.sh, or export it for the stack you\n"
            "       mean. There is deliberately no default: this used to fall back to\n"
            "       the production catalog, which is not a thing to guess at.")
    return TABLE


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
    action = {"TableName": table(), "Item": to_item(doc)}
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
    for page in paginator.paginate(TableName=table(), **kwargs):
        for item in page.get("Items", []):
            yield from_item(item)


def table_exists(ddb) -> bool:
    try:
        ddb.describe_table(TableName=table())
    except ddb.exceptions.ResourceNotFoundException:
        return False
    return True
