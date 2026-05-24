"""
Events API Lambda Function

Serves a REST API via API Gateway for querying events stored in DynamoDB.

Endpoints:
  GET  /api/events          - List events (optional ?upcoming=true filter)
  GET  /api/events/{id}     - Get a single event by event_id
  GET  /api/admin/emails    - List all processed emails (admin dashboard)
  OPTIONS /*                - CORS preflight

Route prefix is /api/... so prod (scout-api.andreas.services) and PR previews
(scout-api-pr.andreas.services/<N>) share the same route definitions — in both
cases the API Gateway base path mapping strips everything before /api.
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import unquote

import boto3
from boto3.dynamodb.conditions import Attr

import taxonomy

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_SUFFIX = os.environ.get("SCOUT_TABLE_SUFFIX", "")
_EVENTS_TABLE = f"scout-events{_SUFFIX}"
_EMAILS_TABLE = f"scout-emails{_SUFFIX}"
_SENDERS_TABLE = f"scout-senders{_SUFFIX}"
_REGIONS_TABLE = f"scout-regions{_SUFFIX}"
_CATEGORIES_TABLE = f"scout-categories{_SUFFIX}"

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(_EVENTS_TABLE)
emails_table = dynamodb.Table(_EMAILS_TABLE)
senders_table = dynamodb.Table(_SENDERS_TABLE)
regions_table = dynamodb.Table(_REGIONS_TABLE)
categories_table = dynamodb.Table(_CATEGORIES_TABLE)

# Editable event fields accepted by the admin PUT endpoint.
_EDITABLE_EVENT_FIELDS = (
    "event_name", "date", "time", "venue", "price", "description", "links",
    "categories", "regions",
)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Content-Type": "application/json",
}


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

class DecimalEncoder(json.JSONEncoder):
    """Convert DynamoDB Decimal values to native Python int/float."""

    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def dumps(obj):
    return json.dumps(obj, cls=DecimalEncoder)


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def ok(body):
    return {"statusCode": 200, "headers": CORS_HEADERS, "body": dumps(body)}


def not_found(message="Not found"):
    return {"statusCode": 404, "headers": CORS_HEADERS, "body": dumps({"error": message})}


def bad_request(message="Bad request"):
    return {"statusCode": 400, "headers": CORS_HEADERS, "body": dumps({"error": message})}


def server_error(message="Internal server error"):
    return {"statusCode": 500, "headers": CORS_HEADERS, "body": dumps({"error": message})}


def cors_preflight():
    return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}


# ---------------------------------------------------------------------------
# Business logic
# ---------------------------------------------------------------------------

def sort_events(events):
    """Sort events: dated events first (ascending), then undated."""
    dated = [e for e in events if e.get("date")]
    undated = [e for e in events if not e.get("date")]
    dated.sort(key=lambda e: e["date"])
    return dated + undated


def _fetch_email_data(email_ids):
    """
    BatchGetItem on scout-emails for a set of email_ids.
    Returns a dict mapping email_id -> email record.
    """
    if not email_ids:
        return {}

    keys = [{"email_id": eid} for eid in email_ids]
    email_map = {}

    # BatchGetItem supports up to 100 keys per call
    for i in range(0, len(keys), 100):
        batch = keys[i:i + 100]
        response = dynamodb.batch_get_item(
            RequestItems={
                _EMAILS_TABLE: {"Keys": batch}
            }
        )
        for item in response.get("Responses", {}).get(_EMAILS_TABLE, []):
            email_map[item["email_id"]] = item

    return email_map


def _merge_email_fields(event, email_map):
    """Attach email metadata fields to an event dict, if available."""
    email_data = email_map.get(event.get("email_id"), {})
    event["image_url"] = email_data.get("image_url", "")
    event["email_subject"] = email_data.get("email_subject", "")
    event["email_sender"] = email_data.get("email_sender", "")
    event["source_email_date"] = email_data.get("source_email_date", "")
    return event


def _scan_all(tbl, filter_expression=None):
    """Scan a table fully, following pagination. Returns all matching items."""
    kwargs = {}
    if filter_expression is not None:
        kwargs["FilterExpression"] = filter_expression
    result = tbl.scan(**kwargs)
    items = result.get("Items", [])
    while "LastEvaluatedKey" in result:
        result = tbl.scan(ExclusiveStartKey=result["LastEvaluatedKey"], **kwargs)
        items.extend(result.get("Items", []))
    return items


def get_all_events(upcoming_only=False, region=None, category=None):
    """
    Return published events for the public site, joined with email metadata.

    Always restricts to status=published (the admin approval gate). Optional
    region/category filters narrow further; region-less events therefore never
    surface under a region filter (the "hidden until classified" rule).
    """
    expr = Attr("status").eq("published")
    if upcoming_only:
        expr = expr & Attr("date").gte(date.today().isoformat())
    if region:
        expr = expr & Attr("regions").contains(region)
    if category:
        expr = expr & Attr("categories").contains(category)

    items = _scan_all(table, expr)

    unique_email_ids = {item["email_id"] for item in items if item.get("email_id")}
    email_map = _fetch_email_data(unique_email_ids)

    events = [_merge_email_fields(item, email_map) for item in items]
    return sort_events(events)


def get_regions():
    """Region registry entries that have at least one published event, with counts."""
    counts = {}
    for ev in _scan_all(table, Attr("status").eq("published")):
        for slug in ev.get("regions") or []:
            counts[slug] = counts.get(slug, 0) + 1

    regions = []
    for reg in _scan_all(regions_table):
        slug = reg["slug"]
        if counts.get(slug, 0) > 0:
            regions.append({"slug": slug, "name": reg.get("name", slug), "count": counts[slug]})
    regions.sort(key=lambda r: (-r["count"], r["name"]))
    return regions


def get_categories():
    """Active categories with published-event counts, for the public filter."""
    counts = {}
    for ev in _scan_all(table, Attr("status").eq("published")):
        for slug in ev.get("categories") or []:
            counts[slug] = counts.get(slug, 0) + 1

    categories = []
    for cat in _scan_all(categories_table, Attr("status").eq("active")):
        slug = cat["slug"]
        categories.append({"slug": slug, "name": cat.get("name", slug), "count": counts.get(slug, 0)})
    categories.sort(key=lambda c: c["name"])
    return categories


def get_event_by_id(event_id):
    """Retrieve a single event by its primary key, joined with email metadata."""
    result = table.get_item(Key={"event_id": event_id})
    event = result.get("Item")
    if event is None:
        return None

    email_id = event.get("email_id", "")
    if email_id:
        email_result = emails_table.get_item(Key={"email_id": email_id})
        email_data = email_result.get("Item", {})
        event["image_url"] = email_data.get("image_url", "")
        event["email_subject"] = email_data.get("email_subject", "")
        event["email_sender"] = email_data.get("email_sender", "")
        event["source_email_date"] = email_data.get("source_email_date", "")

    return event


def get_all_emails():
    """Scan scout-emails and return all processed emails, newest first."""
    result = emails_table.scan()
    items = result.get("Items", [])

    while "LastEvaluatedKey" in result:
        result = emails_table.scan(ExclusiveStartKey=result["LastEvaluatedKey"])
        items.extend(result.get("Items", []))

    items.sort(key=lambda e: e.get("processed_at", ""), reverse=True)
    return items


# ---------------------------------------------------------------------------
# Admin operations (protected by the API Gateway Cognito authorizer)
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def list_admin_events(status=None):
    """All events (any status/region), newest-reviewed first, for the admin queue."""
    expr = Attr("status").eq(status) if status and status != "all" else None
    items = _scan_all(table, expr)
    unique_email_ids = {i["email_id"] for i in items if i.get("email_id")}
    email_map = _fetch_email_data(unique_email_ids)
    events = [_merge_email_fields(i, email_map) for i in items]
    return sort_events(events)


def set_event_status(event_id, status, reviewer=None):
    """Transition an event's status (approve/reject/unpublish). Returns the event or None."""
    if table.get_item(Key={"event_id": event_id}).get("Item") is None:
        return None
    table.update_item(
        Key={"event_id": event_id},
        UpdateExpression="SET #s = :s, reviewed_at = :t, reviewed_by = :r",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":t": _now_iso(), ":r": reviewer or "admin"},
    )
    return get_event_by_id(event_id)


def update_event(event_id, payload):
    """Edit allowed fields on any event in any state. Returns the event or None."""
    if table.get_item(Key={"event_id": event_id}).get("Item") is None:
        return None
    updates = {k: payload[k] for k in _EDITABLE_EVENT_FIELDS if k in payload}
    if updates:
        names = {f"#{k}": k for k in updates}
        values = {f":{k}": v for k, v in updates.items()}
        set_expr = ", ".join(f"#{k} = :{k}" for k in updates)
        table.update_item(
            Key={"event_id": event_id},
            UpdateExpression=f"SET {set_expr}",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    return get_event_by_id(event_id)


def list_senders(status=None):
    """Sender classifications, for the pending-sender queue / management view."""
    expr = Attr("status").eq(status) if status and status != "all" else None
    items = _scan_all(senders_table, expr)
    items.sort(key=lambda s: s.get("first_seen", ""), reverse=True)
    return items


def _retag_events_for_sender(sender_key, regions):
    """Set `regions` on every event from a sender (and its email records)."""
    for ev in _scan_all(table, Attr("sender_key").eq(sender_key)):
        table.update_item(
            Key={"event_id": ev["event_id"]},
            UpdateExpression="SET #r = :r",
            ExpressionAttributeNames={"#r": "regions"},
            ExpressionAttributeValues={":r": regions},
        )
    for em in _scan_all(emails_table, Attr("sender_key").eq(sender_key)):
        emails_table.update_item(
            Key={"email_id": em["email_id"]},
            UpdateExpression="SET #r = :r",
            ExpressionAttributeNames={"#r": "regions"},
            ExpressionAttributeValues={":r": regions},
        )


def _ensure_regions_exist(regions):
    """Create any missing region registry rows (slug + humanized name)."""
    for slug in regions:
        if regions_table.get_item(Key={"slug": slug}).get("Item") is None:
            regions_table.put_item(Item={
                "slug": slug,
                "name": slug.replace("-", " ").title(),
                "created_at": _now_iso(),
            })


def classify_sender(sender_key, payload):
    """
    Assign region(s) to a sender, mark it classified, register any new regions,
    and re-tag the sender's existing events so they become visible.
    """
    regions = payload.get("regions") or []
    display = payload.get("display_sender", sender_key)
    _ensure_regions_exist(regions)
    senders_table.update_item(
        Key={"sender_key": sender_key},
        UpdateExpression="SET #r = :r, #s = :s, display_sender = if_not_exists(display_sender, :d), updated_at = :t",
        ExpressionAttributeNames={"#r": "regions", "#s": "status"},
        ExpressionAttributeValues={
            ":r": regions, ":s": "classified", ":d": display, ":t": _now_iso(),
        },
    )
    _retag_events_for_sender(sender_key, regions)
    return senders_table.get_item(Key={"sender_key": sender_key}).get("Item")


def list_admin_categories(status=None):
    """Category registry, optionally filtered to suggested/active for the review queue."""
    expr = Attr("status").eq(status) if status and status != "all" else None
    items = _scan_all(categories_table, expr)
    items.sort(key=lambda c: c.get("name", c["slug"]))
    return items


def upsert_category(payload):
    """Approve/create a category as active (optionally renaming a suggested one)."""
    slug = payload.get("slug") or taxonomy.slugify(payload.get("name", ""))
    if not slug:
        return None
    existing = categories_table.get_item(Key={"slug": slug}).get("Item")
    name = payload.get("name") or (existing or {}).get("name") or slug
    categories_table.put_item(Item={
        "slug": slug,
        "name": name,
        "status": "active",
        "created_at": (existing or {}).get("created_at", _now_iso()),
    })
    return categories_table.get_item(Key={"slug": slug}).get("Item")


def delete_category(slug):
    """Reject/remove a category. Chips already hide non-active slugs, so events are left as-is."""
    categories_table.delete_item(Key={"slug": slug})


# ---------------------------------------------------------------------------
# Request routing
# ---------------------------------------------------------------------------

def _normalize_route(event):
    """
    Return the request path relative to /api (with a leading slash), e.g.
    "/events", "/events/abc", "/admin/senders/x@y.com".

    Works whether the request arrived on an explicit resource or the
    `{proxy+}` catch-all, and regardless of any custom-domain base path,
    because we anchor on the "/api/" segment in the full path.
    """
    raw = event.get("path") or event.get("resource") or ""
    idx = raw.find("/api/")
    if idx >= 0:
        return raw[idx + len("/api"):]
    if raw in ("/api", ""):
        return "/"
    return raw


def _segments(route):
    return [unquote(p) for p in route.strip("/").split("/") if p != ""]


def _parse_body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _route_public(method, route, query):
    if method != "GET":
        return None
    if route == "/events":
        upcoming = (query or {}).get("upcoming", "").lower() == "true"
        events = get_all_events(
            upcoming_only=upcoming,
            region=(query or {}).get("region"),
            category=(query or {}).get("category"),
        )
        return ok({"events": events, "count": len(events)})
    if route.startswith("/events/"):
        event_id = unquote(route[len("/events/"):])
        if not event_id:
            return bad_request("Missing event ID")
        ev = get_event_by_id(event_id)
        return ok(ev) if ev is not None else not_found(f"Event {event_id!r} not found")
    if route == "/regions":
        regions = get_regions()
        return ok({"regions": regions, "count": len(regions)})
    if route == "/categories":
        categories = get_categories()
        return ok({"categories": categories, "count": len(categories)})
    return None


def _route_admin(method, parts, query, body):
    """parts begins with 'admin'. Auth is enforced by the API Gateway authorizer."""
    sub = parts[1:]

    if sub == ["emails"] and method == "GET":
        emails = get_all_emails()
        return ok({"emails": emails, "count": len(emails)})

    if sub and sub[0] == "events":
        rest = sub[1:]
        if rest == [] and method == "GET":
            events = list_admin_events(status=(query or {}).get("status"))
            return ok({"events": events, "count": len(events)})
        if rest == ["approve"] and method == "POST":  # bulk
            ids = body.get("ids") or []
            for eid in ids:
                set_event_status(eid, "published")
            return ok({"approved": len(ids)})
        if len(rest) == 1 and method == "PUT":  # edit any field
            ev = update_event(rest[0], body)
            return ok(ev) if ev is not None else not_found("Event not found")
        if len(rest) == 2 and method == "POST" and rest[1] in ("approve", "reject", "unpublish"):
            new_status = {"approve": "published", "reject": "rejected", "unpublish": "pending"}[rest[1]]
            ev = set_event_status(rest[0], new_status)
            return ok(ev) if ev is not None else not_found("Event not found")

    if sub and sub[0] == "senders":
        rest = sub[1:]
        if rest == [] and method == "GET":
            senders = list_senders(status=(query or {}).get("status"))
            return ok({"senders": senders, "count": len(senders)})
        if len(rest) == 1 and method == "PUT":
            return ok(classify_sender(rest[0], body))

    if sub and sub[0] == "categories":
        rest = sub[1:]
        if rest == [] and method == "GET":
            categories = list_admin_categories(status=(query or {}).get("status"))
            return ok({"categories": categories, "count": len(categories)})
        if rest == [] and method == "POST":
            cat = upsert_category(body)
            return ok(cat) if cat is not None else bad_request("Missing category name")
        if len(rest) == 1 and method == "DELETE":
            delete_category(rest[0])
            return ok({"deleted": rest[0]})

    return not_found("Unknown admin endpoint")


def route_request(event):
    """Dispatch based on HTTP method and the path relative to /api."""
    method = event.get("httpMethod", "GET")
    if method == "OPTIONS":
        return cors_preflight()

    route = _normalize_route(event)
    parts = _segments(route)
    query = event.get("queryStringParameters") or {}

    if parts and parts[0] == "admin":
        return _route_admin(method, parts, query, _parse_body(event))

    public = _route_public(method, route, query)
    return public if public is not None else not_found("Unknown endpoint")


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event))

    try:
        # Routing anchors on the "/api/" segment of event["path"], so it works
        # for explicit resources, the {proxy+} catch-all, and custom-domain base
        # paths alike (e.g. scout-api-pr.andreas.services/33/api/events).
        return route_request(event)

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return server_error(str(exc))
