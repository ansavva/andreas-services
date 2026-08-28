# The catalog table's client, plus the item marshalling every caller needs.
#
# Credentials come from `s3.py`. That module resolves a *session*, not an S3
# session, so this one asks it rather than solving the same problem twice. The
# indirection mattered more before August 2026, when boto3's own chain could not
# see the AWS CLI's `aws login` credentials and the bridge there was the only
# way to get any; with a long-lived access key boto3 would now manage alone.
#
# Nothing here knows what a node or a library is. That is `maintenance/
# catalog_check.py`'s subject; this is the outside world, in `adapters/`.
# (It named `catalog_seed.py` until that one-shot was retired with the layout
# it inventoried.)
from __future__ import annotations

from studio_pipeline import profiles
from studio_pipeline.adapters import s3 as s3c

# **The table is a PROFILE FIELD now** (`profiles.py`); `TABLE` is gone.
#
# It read `os.environ.get("STUDIO_CATALOG_TABLE", "studio-prod-catalog")`,
# justified at the time by studio having exactly one environment that local runs
# addressed. `studio/CLAUDE.md` said the opposite long before this module caught
# up — the CLI targets a per-machine dev stack — so the default meant a
# maintenance command run in a shell that had not loaded `studio/.env` addressed
# the PRODUCTION catalog. One of the readers is `catalog gc`, which deletes: a
# dry run against the wrong table calls prod's blobs unreferenced, and the
# `--apply` that follows removes them. That default was removed with the
# matching one in `adapters/s3.py` (#434), and it was latent only because every
# command reading both asks `s3c.bucket()` first and dies there — call ordering,
# not a guard.
#
# The environment variable is still read, as the fallback when no profile is
# selected. Names still follow `[project]-[env]-[component]`.


def table() -> str:
    """The catalog table, or a refusal naming what to do about it.

    Asked for through here rather than read off a module constant, exactly as
    `s3.bucket()` is, so "unset" cannot be discovered halfway through a
    paginate — and so that the profile an invocation selected is what answers.
    `TABLE = os.environ.get(...)` was bound at import time, which is before
    Click has parsed `--profile`; see the note in `adapters/s3.py`.
    """
    return profiles.value("catalog_table")


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

    **Every `float` becomes a `Decimal`, and it has to happen here.**
    `TypeSerializer` refuses a float outright — DynamoDB's N is a decimal type
    and boto3 will not guess a binary-float rounding for you — so a document
    containing one raised `TypeError: Float types are not supported` from three
    frames inside boto3, naming nothing about which attribute was at fault.

    Nothing that came through here held a float until `catalog backfill-plans`
    started writing a run's PARAMS, which are whatever the model was given:
    `topazlabs/image-upscale` takes `face_enhancement_strength: 0.8`, and 131 of
    production's 254 runs are upscales. It was caught by trialling the backfill
    on a single run, which is what `--limit` is for.

    The conversion goes through `str`, so 0.8 is stored as 0.8 rather than as
    the seventeen digits its binary representation actually is. **This mirrors
    `services/catalog.py::_decimals` deliberately** — the backend hit the same
    wall when a run started recording what a prediction cost — and `from_item`
    below is the inverse on the way out.
    """
    import decimal

    from boto3.dynamodb.types import TypeSerializer

    def decimals(value):
        if isinstance(value, float):
            return decimal.Decimal(str(value))
        if isinstance(value, dict):
            return {k: decimals(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [decimals(v) for v in value]
        return value

    serializer = TypeSerializer()
    return {k: serializer.serialize(decimals(v))
            for k, v in doc.items() if v is not None}


def to_map(doc: dict) -> dict:
    """A dict -> a typed map with its `None`s KEPT as NULL.

    **The difference from `to_item` is the whole reason this exists.** That one
    drops a `None` because an absent attribute is what the node schema means by
    "this folder has no blob key" — and `attribute_not_exists` is what enforces
    uniqueness, so writing NULLs there would quietly defeat it.

    A **value map** is the opposite case. `plan` holds whatever a person chose,
    and `prompt: None` is a real answer for a model that takes no prompt —
    `topazlabs/image-upscale` is 131 of production's 254 runs. Dropping it makes
    a stored plan a different document from the one that was hashed, so
    `plan_digest` disagrees with the plan sitting beside it: `catalog verify`
    reports `stale_plan_digest`, and every one of those runs tells a person on
    its own page that the payload changed after it was approved, which is a lie
    about work nobody touched.

    It also has to match what the BACKEND writes for an authored plan.
    `services/catalog.py` serialises through `TypeSerializer` without dropping,
    so `submit.py`'s `plan_of` stores `prompt: NULL` for a promptless model. Two
    writers producing two shapes of one document would give identical payloads
    two different digests.
    """
    import decimal

    from boto3.dynamodb.types import TypeSerializer

    def decimals(value):
        if isinstance(value, float):
            return decimal.Decimal(str(value))
        if isinstance(value, dict):
            return {k: decimals(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [decimals(v) for v in value]
        return value

    return {k: TypeSerializer().serialize(decimals(v)) for k, v in doc.items()}


def from_item(item: dict) -> dict:
    """The inverse, with numbers as ints.

    The deserializer returns `Decimal` for every N, which compares equal to an
    int but formats as `Decimal('12')` in a report and is not JSON-serialisable
    — and this command's whole output is a journal file.

    **It recurses, and the version that did not was a real bug.** The
    conversion used to run over the top-level attributes only, which was
    invisible for as long as every row this read was flat: a node row's numbers
    are `size` and nothing else. An ENTITY row is not flat — a character carries
    a nested `profile` and a project carries `counts` — so `dev-seed publish`
    read a `schema_version` sitting two maps deep, handed it to `json.dumps`,
    and died with "Object of type Decimal is not JSON serializable" halfway
    through writing the fixture. Lists count too: `default_set` is a list, and a
    list of numbers had the same hole.
    """
    import decimal

    from boto3.dynamodb.types import TypeDeserializer

    def plain(value):
        if isinstance(value, decimal.Decimal):
            return (int(value) if value == value.to_integral_value()
                    else float(value))
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        if isinstance(value, set):
            # A DynamoDB set deserialises to a `set`, which json.dumps also
            # refuses. Sorted rather than arbitrary, so a journal file diffs.
            return sorted(plain(v) for v in value)
        return value

    deserializer = TypeDeserializer()
    return {key: plain(deserializer.deserialize(value))
            for key, value in item.items()}


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
