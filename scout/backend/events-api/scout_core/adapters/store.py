"""
Single-table data-access layer for the scout-core DynamoDB table.

scout-core holds the full entity graph (sources, source-runs, events,
sub-events, locations, the three label taxonomies, and their M2M junction
items) keyed by a generic PK/SK with five shared GSIs. This module owns key
construction, the generic read/write primitives, soft-delete scoping, and the
cascade-aware soft-delete / restore mechanics.

It is intentionally self-contained (no shared package) so it can be copied into
each Lambda image, matching the taxonomy.py convention.
"""

import os
import time
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

_SUFFIX = os.environ.get("SCOUT_TABLE_SUFFIX", "")
CORE_TABLE = f"scout-core{_SUFFIX}"
SETTINGS_TABLE = f"scout-settings{_SUFFIX}"

# ---------------------------------------------------------------------------
# Entity types (the `entity_type` attribute stamped on every item)
# ---------------------------------------------------------------------------
SOURCE = "source"
RUN = "run"
EVENT = "event"
SUBEVENT = "subevent"
LOCATION = "location"
SOURCE_LABEL = "source_label"
EVENT_LABEL = "event_label"
LOCATION_LABEL = "location_label"
SOURCE_LABEL_LINK = "src_label_link"
EVENT_LABEL_LINK = "evt_label_link"
LOCATION_LABEL_LINK = "loc_label_link"

DELETED_AT = "deleted_at"

# GSI key attributes that index live, public-facing or dedup-critical rows.
# Soft-delete REMOVEs these so deleted items fall out of those hot paths with no
# filter; the entity layer re-adds them on restore when the item still qualifies.
HOT_INDEX_ATTRS = ("GSI1PK", "GSI1SK", "GSI3PK", "GSI3SK")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_dynamodb = None


def _region():
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


# ---------------------------------------------------------------------------
# Resource / table handles (lazy so importing under moto/tests is side-effect free)
# ---------------------------------------------------------------------------

def _resource():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=_region())
    return _dynamodb


def core():
    return _resource().Table(CORE_TABLE)


def settings_table():
    return _resource().Table(SETTINGS_TABLE)


# ---------------------------------------------------------------------------
# Identifiers & timestamps
# ---------------------------------------------------------------------------

def new_id():
    """Generate a 26-char ULID (Crockford base32) — lexicographically sortable
    by creation time, so SKs that embed an id order chronologically."""
    ts = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ts << 80) | rand
    chars = [""] * 26
    for i in range(25, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------

_LABEL_PREFIX = {
    SOURCE_LABEL: "SLBL#",
    EVENT_LABEL: "ELBL#",
    LOCATION_LABEL: "LLBL#",
}

_ENTITY_REF_PREFIX = {
    SOURCE: "SRC#",
    EVENT: "EVT#",
    SUBEVENT: "SUB#",
    LOCATION: "LOC#",
}


def source_pk(source_id):
    return f"SRC#{source_id}"


def event_pk(event_id):
    return f"EVT#{event_id}"


def location_pk(location_id):
    return f"LOC#{location_id}"


def label_pk(taxonomy, label_id):
    """Partition key for a label in one of the three taxonomies."""
    return f"{_LABEL_PREFIX[taxonomy]}{label_id}"


def run_sk(run_id):
    """Source-run SK; run_id is a ULID, so querying ScanIndexForward=False under
    the source partition yields runs newest-first."""
    return f"RUN#{run_id}"


def sub_sk(start_date, subevent_id):
    """Sub-event SK embeds its start date for free chronological ordering."""
    return f"SUB#{start_date}#{subevent_id}"


def entity_ref(entity_type, entity_id):
    """Stable reference string for an entity (used as GSI2 partition + in links)."""
    return f"{_ENTITY_REF_PREFIX[entity_type]}{entity_id}"


def link_sk(entity_type, entity_id):
    """SK of a label->entity junction item, stored in the label's partition."""
    return f"LINK#{entity_ref(entity_type, entity_id)}"


# ---------------------------------------------------------------------------
# Item construction
# ---------------------------------------------------------------------------

def base_item(pk, sk, entity_type, **attrs):
    """Build an item envelope with the standard PK/SK/entity_type/created_at."""
    item = {"PK": pk, "SK": sk, "entity_type": entity_type, "created_at": now_iso()}
    item.update({k: v for k, v in attrs.items() if v is not None})
    return item


# ---------------------------------------------------------------------------
# Generic reads / writes
# ---------------------------------------------------------------------------

def put(item):
    core().put_item(Item=item)
    return item


def get(pk, sk):
    return core().get_item(Key={"PK": pk, "SK": sk}).get("Item")


def set_attrs(pk, sk, attrs):
    """SET the given attributes on an item. Uses name placeholders so reserved
    words (e.g. `name`, `status`) are safe. No-op for an empty mapping."""
    if not attrs:
        return
    keys = list(attrs)
    names = {f"#k{i}": k for i, k in enumerate(keys)}
    values = {f":v{i}": attrs[k] for i, k in enumerate(keys)}
    set_expr = ", ".join(f"#k{i} = :v{i}" for i in range(len(keys)))
    core().update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression="SET " + set_expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def append_to_list(pk, sk, attr, value):
    """Append one element to a list attribute, creating the list when absent.
    Atomic (no read-modify-write), so concurrent appends don't clobber."""
    core().update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression="SET #a = list_append(if_not_exists(#a, :empty), :item)",
        ExpressionAttributeNames={"#a": attr},
        ExpressionAttributeValues={":empty": [], ":item": [value]},
    )


def remove_attrs(pk, sk, attr_names):
    """REMOVE the given attributes from an item. No-op for an empty list."""
    names = list(attr_names)
    if not names:
        return
    placeholders = {f"#r{i}": n for i, n in enumerate(names)}
    core().update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression="REMOVE " + ", ".join(placeholders),
        ExpressionAttributeNames=placeholders,
    )


def delete(pk, sk):
    """Hard-delete a single item (used for ephemeral edges like detaching a
    label or moving a location pointer — entity rows are always soft-deleted)."""
    core().delete_item(Key={"PK": pk, "SK": sk})


def query_all(pk, *, sk_begins_with=None, live_only=True, ascending=True):
    """Query a base-table partition, following pagination. Returns a list."""
    cond = Key("PK").eq(pk)
    if sk_begins_with is not None:
        cond = cond & Key("SK").begins_with(sk_begins_with)
    kwargs = {"KeyConditionExpression": cond, "ScanIndexForward": ascending}
    if live_only:
        kwargs["FilterExpression"] = Attr(DELETED_AT).not_exists()
    return _drain(kwargs)


def query_index_all(index, pk, *, sk_begins_with=None, live_only=True, ascending=True):
    """Query a GSI partition fully. Returns a list."""
    cond = Key(f"{index}PK").eq(pk)
    if sk_begins_with is not None:
        cond = cond & Key(f"{index}SK").begins_with(sk_begins_with)
    kwargs = {
        "IndexName": index,
        "KeyConditionExpression": cond,
        "ScanIndexForward": ascending,
    }
    if live_only:
        kwargs["FilterExpression"] = Attr(DELETED_AT).not_exists()
    return _drain(kwargs)


def query_index_page(index, pk, *, sk_begins_with=None, live_only=True,
                     ascending=True, limit=None, start_key=None):
    """Single GSI page for cursor pagination. Returns (items, next_start_key)."""
    cond = Key(f"{index}PK").eq(pk)
    if sk_begins_with is not None:
        cond = cond & Key(f"{index}SK").begins_with(sk_begins_with)
    kwargs = {
        "IndexName": index,
        "KeyConditionExpression": cond,
        "ScanIndexForward": ascending,
    }
    if live_only:
        kwargs["FilterExpression"] = Attr(DELETED_AT).not_exists()
    if limit is not None:
        kwargs["Limit"] = limit
    if start_key is not None:
        kwargs["ExclusiveStartKey"] = start_key
    resp = core().query(**kwargs)
    return resp.get("Items", []), resp.get("LastEvaluatedKey")


def query_page(pk, *, sk_begins_with=None, live_only=True, ascending=True,
               limit=None, start_key=None):
    """Single base-table page for cursor pagination. Returns (items, next_start_key)."""
    cond = Key("PK").eq(pk)
    if sk_begins_with is not None:
        cond = cond & Key("SK").begins_with(sk_begins_with)
    kwargs = {"KeyConditionExpression": cond, "ScanIndexForward": ascending}
    if live_only:
        kwargs["FilterExpression"] = Attr(DELETED_AT).not_exists()
    if limit is not None:
        kwargs["Limit"] = limit
    if start_key is not None:
        kwargs["ExclusiveStartKey"] = start_key
    resp = core().query(**kwargs)
    return resp.get("Items", []), resp.get("LastEvaluatedKey")


# ---------------------------------------------------------------------------
# Cursor encoding (opaque round-trip of DynamoDB LastEvaluatedKey)
# ---------------------------------------------------------------------------

def encode_cursor(last_key):
    """Opaque base64(JSON) wrapper around a DynamoDB LastEvaluatedKey.

    Returns None when there is no more data. Decimals (DynamoDB number type)
    are stringified so the JSON round-trip is lossless.
    """
    if not last_key:
        return None
    import base64  # noqa: PLC0415  (rare path)
    import json  # noqa: PLC0415

    def _default(o):
        from decimal import Decimal  # noqa: PLC0415
        if isinstance(o, Decimal):
            return str(o)
        raise TypeError(f"unserializable: {type(o)}")

    payload = json.dumps(last_key, default=_default, sort_keys=True)
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor):
    """Inverse of `encode_cursor`. Returns None for missing/invalid cursors so
    the caller can treat 'no cursor' and 'bad cursor' the same — start from
    the beginning."""
    if not cursor:
        return None
    import base64  # noqa: PLC0415
    import json  # noqa: PLC0415
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, TypeError):
        return None


def _drain(kwargs):
    resp = core().query(**kwargs)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        resp = core().query(**kwargs)
        items.extend(resp.get("Items", []))
    return items


# ---------------------------------------------------------------------------
# Soft delete / restore
# ---------------------------------------------------------------------------

def soft_delete(pk, sk, entity_type, *, cascade_id=None, via_cascade=False,
                parent_ref=None, hot_index_attrs=HOT_INDEX_ATTRS):
    """Mark an item soft-deleted: stamp deleted_at + cascade metadata, enroll it
    in the GSI5 deleted-view, and REMOVE its hot-path index keys (GSI1/GSI3) so
    it drops out of the public and dedup paths."""
    now = now_iso()
    set_parts = ["#d = :d", "GSI5PK = :g5pk", "GSI5SK = :g5sk"]
    names = {"#d": DELETED_AT}
    values = {":d": now, ":g5pk": f"DELETED#{entity_type}", ":g5sk": now}
    if via_cascade:
        set_parts.append("deleted_via_cascade = :vc")
        values[":vc"] = True
    if cascade_id is not None:
        set_parts.append("cascade_id = :cid")
        values[":cid"] = cascade_id
    if parent_ref is not None:
        set_parts.append("deleted_parent_ref = :pr")
        values[":pr"] = parent_ref
    expr = "SET " + ", ".join(set_parts)
    if hot_index_attrs:
        expr += " REMOVE " + ", ".join(hot_index_attrs)
    core().update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def restore(pk, sk):
    """Clear soft-delete markers and drop the item out of the GSI5 deleted-view.
    Re-adding the status-dependent hot index keys (GSI1/GSI3) is the entity
    layer's responsibility, since it depends on the item's own current status."""
    core().update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression=(
            "REMOVE #d, deleted_via_cascade, cascade_id, deleted_parent_ref, "
            "GSI5PK, GSI5SK"
        ),
        ExpressionAttributeNames={"#d": DELETED_AT},
    )


def scan_by_type(entity_type, *, live_only=True):
    """Full-table scan filtered to one entity type. Admin/cron use only (e.g.
    the past-status sweep) — not a hot path."""
    expr = Attr("entity_type").eq(entity_type)
    if live_only:
        expr = expr & Attr(DELETED_AT).not_exists()
    resp = core().scan(FilterExpression=expr)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = core().scan(FilterExpression=expr,
                           ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def query_deleted(entity_type, *, ascending=False):
    """List soft-deleted items of one entity type (the deleted-filter view)."""
    return query_index_all(
        "GSI5", f"DELETED#{entity_type}", live_only=False, ascending=ascending
    )


# ---------------------------------------------------------------------------
# System settings (singleton, cached at module scope)
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "system_timezone": "UTC",
    "fallback_timezone": "UTC",
    "past_grace_hours": 24,
    "health_zero_event_runs": 3,
    "health_overdue_hours": 26,
    "link_follow_cap": 10,
    "default_agent_model": "claude-haiku-4-5",
    "default_agent_budget_tokens": 200000,
    "default_agent_budget_seconds": 120,
}

_settings_cache = None


def get_settings(refresh=False):
    """Return system settings (stored values merged over defaults), cached."""
    global _settings_cache
    if _settings_cache is not None and not refresh:
        return _settings_cache
    item = settings_table().get_item(Key={"setting_id": "system"}).get("Item") or {}
    merged = dict(DEFAULT_SETTINGS)
    for key, value in item.items():
        if key != "setting_id":
            merged[key] = value
    _settings_cache = merged
    return merged


def put_settings(values):
    """Persist (partial) settings and invalidate the cache."""
    global _settings_cache
    item = {"setting_id": "system"}
    item.update({k: v for k, v in values.items() if k != "setting_id"})
    settings_table().put_item(Item=item)
    _settings_cache = None
    return get_settings(refresh=True)


def reset_settings_cache():
    """Test/aid hook to drop the in-process settings cache."""
    global _settings_cache
    _settings_cache = None
