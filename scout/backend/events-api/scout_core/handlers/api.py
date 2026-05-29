"""
Events API Lambda — HTTP router over the scout-core service layer.

Public endpoints (no auth) back the end-user UI; admin endpoints
(/api/admin/*, behind the API Gateway Cognito authorizer) back the admin
console. Routing anchors on the "/api/" path segment so the one Lambda serves
explicit resources, the {proxy+} catch-all and any custom-domain base path
(prod and PR previews alike).

This delegates to the domain modules (sources, runs, events, locations, labels,
images, deletion, notifications, public, store); it holds no business logic of
its own beyond request/response plumbing.
"""

import json
import logging
import os
from decimal import Decimal
from urllib.parse import unquote

import boto3

from scout_core.domain import deletion
from scout_core.domain import events
from scout_core.domain import images
from scout_core.domain import labels
from scout_core.domain import locations
from scout_core.domain import notifications
from scout_core.domain import public
from scout_core.domain import runs
from scout_core.domain import sources
from scout_core.adapters import artifacts
from scout_core.adapters import image_store
from scout_core.adapters import store
from scout_core.common import config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_SUFFIX = os.environ.get("SCOUT_TABLE_SUFFIX", "")
_PROCESSOR_FN = os.environ.get("SCOUT_PROCESSOR_FN", f"scout-source-run-processor{_SUFFIX}")

_TAXONOMY = {
    "source": store.SOURCE_LABEL,
    "event": store.EVENT_LABEL,
    "location": store.LOCATION_LABEL,
}
_DELETED_TYPES = {
    "source": store.SOURCE, "event": store.EVENT, "subevent": store.SUBEVENT,
    "location": store.LOCATION, "source_label": store.SOURCE_LABEL,
    "event_label": store.EVENT_LABEL, "location_label": store.LOCATION_LABEL,
}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Content-Type": "application/json",
}

_lambda_client = None


def _lambda():
    global _lambda_client
    if _lambda_client is None:
        region = (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        _lambda_client = boto3.client("lambda", region_name=region)
    return _lambda_client


# ---------------------------------------------------------------------------
# Serialization & responses
# ---------------------------------------------------------------------------

class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _resp(status, body):
    return {"statusCode": status, "headers": CORS_HEADERS,
            "body": json.dumps(body, cls=_DecimalEncoder)}


def _binary_resp(status, data, content_type):
    """Raw binary response. API Gateway base64-decodes when it sees the response
    Content-Type in the REST API's `binary_media_types` list."""
    import base64  # noqa: PLC0415
    headers = {**CORS_HEADERS, "Content-Type": content_type}
    return {"statusCode": status, "headers": headers,
            "body": base64.b64encode(data).decode(), "isBase64Encoded": True}


def ok(body):
    return _resp(200, body)


def created(body):
    return _resp(201, body)


def bad_request(message):
    return _resp(400, {"error": message})


def not_found(message="Not found"):
    return _resp(404, {"error": message})


def server_error(message):
    return _resp(500, {"error": message})


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

def _route(event):
    raw = event.get("path") or event.get("resource") or ""
    idx = raw.find("/api/")
    if idx >= 0:
        return raw[idx + len("/api"):]
    return "/" if raw in ("/api", "") else raw


def _segments(route):
    return [unquote(p) for p in route.strip("/").split("/") if p]


def _body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _actor(event):
    """Reviewer identity from the API Gateway Cognito authorizer claims, or None
    (e.g. in PR previews where the authorizer is disabled)."""
    claims = (((event.get("requestContext") or {}).get("authorizer") or {})
              .get("claims") or {})
    return claims.get("email") or claims.get("cognito:username")


def _csv(query, key):
    value = (query or {}).get(key)
    return [v for v in value.split(",") if v] if value else None


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

def _route_public(method, parts, query):
    if method != "GET":
        return None
    rest = parts[1:]
    if rest == ["events"]:
        page = public.feed(
            location_id=(query or {}).get("location_id"),
            event_label_ids=_csv(query, "event_labels"),
            location_label_ids=_csv(query, "location_labels"),
            search=(query or {}).get("q"),
            sort=(query or {}).get("sort", public.SORT_DATE),
            cursor=(query or {}).get("cursor"),
            page_size=int((query or {}).get("page_size", public.DEFAULT_PAGE_SIZE)),
        )
        return ok(page)
    if len(rest) == 2 and rest[0] == "events":
        detail = public.event_detail(rest[1])
        return ok(detail) if detail else not_found("Event not found")
    if rest == ["facets"]:
        return ok(public.facets())
    if len(rest) == 2 and rest[0] == "images":
        data, content_type = image_store.get_bytes(rest[1])
        if data is None:
            return not_found("Image not found")
        return _binary_resp(200, data, content_type)
    return None


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------

# Server-controlled artifact chunk size. Stays well under the ~6 MB Lambda
# response cap even after JSON-string escaping.
_ARTIFACT_CHUNK = 512 * 1024


def _artifact_url(base, source_id, run_id, descriptor):
    """Build an absolute our-domain URL the client can fetch chunks from."""
    path = (f"{base}/admin/sources/{source_id}/runs/{run_id}/artifact"
            f"?kind={descriptor['kind']}")
    if "index" in descriptor:
        path += f"&index={descriptor['index']}"
    return path


def _trigger(source_id, mode):
    _lambda().invoke(
        FunctionName=_PROCESSOR_FN, InvocationType="Event",
        Payload=json.dumps({"source_id": source_id, "mode": mode}).encode(),
    )
    return {"status": "started", "source_id": source_id, "mode": mode}


def _scan_inbox():
    _lambda().invoke(
        FunctionName=_PROCESSOR_FN, InvocationType="Event",
        Payload=json.dumps({"mode": "discover"}).encode(),
    )
    return {"status": "started", "mode": "discover"}


def _admin_sources(method, rest, query, body):
    if rest == [] and method == "GET":
        archived = (query or {}).get("archived") == "true"
        limit = int((query or {}).get("page_size", "50"))
        start_key = store.decode_cursor((query or {}).get("cursor"))
        items, next_key = sources.list_sources_page(
            archived=archived, status=(query or {}).get("status"),
            limit=limit, start_key=start_key,
        )
        running = runs.in_progress_source_ids()
        for item in items:
            item["running"] = item["source_id"] in running
        return ok({"sources": items, "next_cursor": store.encode_cursor(next_key)})
    if rest == ["running"] and method == "GET":
        return ok({"running": sorted(runs.in_progress_source_ids())})
    if rest == [] and method == "POST":
        src = sources.create_source(
            body.get("type"), body.get("identity"), name=body.get("name"),
            config=body.get("config"), follow_links=body.get("follow_links", False),
            agent_model=body.get("agent_model"),
            agent_budget_tokens=body.get("agent_budget_tokens"),
            agent_budget_seconds=body.get("agent_budget_seconds"))
        return created(src)
    if rest == ["health"] and method == "GET":
        return ok(sources.health_report())
    if rest == ["scan-inbox"] and method == "POST":
        return ok(_scan_inbox())

    if not rest:
        return None
    source_id = rest[0]
    action = rest[1:]

    if action == [] and method == "GET":
        src = sources.get_source(source_id)
        return ok(src) if src else not_found("Source not found")
    if action == [] and method == "PUT":
        src = sources.update_source(source_id, body)
        return ok(src) if src else not_found("Source not found")
    if action == [] and method == "DELETE":
        result = deletion.delete_source(
            source_id, cascade_events=(query or {}).get("cascade", "true") != "false")
        return ok(result) if result else not_found("Source not found")
    if action == ["delete-preview"] and method == "GET":
        return ok(deletion.preview_delete_source(source_id))
    if action == ["archive"] and method == "POST":
        return ok(sources.set_archived(source_id, body.get("archived", True)))
    if action == ["runs"] and method == "GET":
        limit = int((query or {}).get("page_size", "20"))
        start_key = store.decode_cursor((query or {}).get("cursor"))
        items, next_key = runs.list_runs_page(
            source_id, limit=limit, start_key=start_key)
        base = config.public_api_base()
        for run in items:
            run["artifacts"] = [
                {**d, "url": _artifact_url(base, source_id, run["run_id"], d)}
                for d in runs.artifact_descriptors(run)
            ]
        return ok({"runs": items, "next_cursor": store.encode_cursor(next_key)})
    if len(action) == 3 and action[0] == "runs" and action[2] == "artifact" \
            and method == "GET":
        run = runs.get_run(source_id, action[1])
        if run is None:
            return not_found("Run not found")
        kind = (query or {}).get("kind", "transcript")
        index = (query or {}).get("index")
        ref = runs.artifact_ref(run, kind, int(index) if index is not None else None)
        if not ref:
            return not_found("Artifact not found")
        offset = int((query or {}).get("offset", "0"))
        chunk = int((query or {}).get("chunk_size", str(_ARTIFACT_CHUNK)))
        text, next_offset, total = artifacts.get_range(ref, offset, chunk)
        return ok({
            "kind": kind, "content": text,
            "offset": offset, "next_offset": next_offset, "total": total,
        })
    if action == ["run"] and method == "POST":
        return ok(_trigger(source_id, "run"))
    if action == ["preview"] and method == "POST":
        return ok(_trigger(source_id, "preview"))
    if action == ["labels"] and method == "POST":
        return ok(sources.add_label(source_id, body["label_id"]))
    if len(action) == 2 and action[0] == "labels" and method == "DELETE":
        sources.remove_label(source_id, action[1])
        return ok({"removed": action[1]})
    return None


def _admin_events(method, rest, query, body):
    if rest == [] and method == "GET":
        review = (query or {}).get("review", events.REVIEW_PENDING)
        limit = int((query or {}).get("page_size", "20"))
        start_key = store.decode_cursor((query or {}).get("cursor"))
        groups, next_key = events.list_review_groups(
            review, limit=limit, start_key=start_key)
        return ok({"groups": groups, "next_cursor": store.encode_cursor(next_key)})
    if rest == ["review"] and method == "POST":  # bulk
        return ok({"updated": len(events.bulk_review(body.get("ids", []),
                                                     body["status"]))})
    if not rest:
        return None

    event_id = rest[0]
    action = rest[1:]
    if action == [] and method == "GET":
        detail = events.admin_detail(event_id)
        return ok(detail) if detail else not_found("Event not found")
    if action == ["preview"] and method == "GET":
        detail = public.preview_detail(event_id)
        return ok(detail) if detail else not_found("Event not found")
    if action == [] and method == "PUT":
        ev = events.update_event(event_id, body)
        return ok(ev) if ev else not_found("Event not found")
    if action == [] and method == "DELETE":
        result = deletion.delete_event(
            event_id, cascade_subs=(query or {}).get("cascade", "true") != "false")
        return ok(result) if result else not_found("Event not found")
    if action == ["review"] and method == "POST":
        return ok(events.set_review(event_id, body["status"]))
    if action == ["decide"] and method == "POST":
        result = events.review_with_feedback(
            event_id, body["decision"],
            feedback=(body.get("feedback") or "").strip() or None,
            author=body.get("_actor"))
        return ok(result) if result else not_found("Event not found")
    if action == ["feedback"] and method == "POST":
        result = events.add_review_feedback(
            event_id, decision=body.get("decision", ""),
            text=body["text"], author=body.get("_actor"))
        return ok(result) if result else not_found("Event not found")
    if action == ["publish"] and method == "POST":
        return ok(events.set_publish(event_id, body.get("published", True)))
    if action == ["cancel"] and method == "POST":
        return ok(events.cancel_event(event_id))
    if action == ["images"] and method == "POST":
        return created(images.add_image(
            store.EVENT, event_id, url=body.get("url"), s3_ref=body.get("s3_ref"),
            source=body.get("source", images.ADMIN)))
    if len(action) == 2 and action[0] == "images" and method == "DELETE":
        images.delete_image(store.EVENT, event_id, action[1])
        return ok({"deleted": action[1]})
    if len(action) == 3 and action[0] == "images" and action[2] == "approve":
        return ok(images.approve_image(store.EVENT, event_id, action[1]))
    return _admin_subevents(method, event_id, action, body)


def _admin_subevents(method, event_id, action, body):
    if action == ["subevents"] and method == "POST":
        return created(events.create_subevent(
            event_id, start_date=body.get("start_date", ""),
            start_time=body.get("start_time"), end_time=body.get("end_time"),
            location_id_override=body.get("location_id_override"),
            event_label_ids=body.get("event_label_ids")))
    if len(action) == 2 and action[0] == "subevents" and method == "PUT":
        result = events.update_subevent(event_id, action[1], body)
        return ok(result) if result else not_found("Sub-event not found")
    if len(action) == 2 and action[0] == "subevents" and method == "DELETE":
        result = deletion.delete_subevent(event_id, action[1])
        return ok(result) if result else not_found("Sub-event not found")
    if len(action) >= 3 and action[0] == "subevents" and method == "POST":
        sub_id, op = action[1], action[2]
        if op == "review":
            return ok(events.set_subevent_review(event_id, sub_id, body["status"]))
        if op == "publish":
            return ok(events.set_subevent_publish(event_id, sub_id,
                                                  body.get("published", True)))
        if op == "cancel":
            return ok(events.cancel_subevent(event_id, sub_id))
    return None


def _admin_locations(method, rest, query, body):
    if rest == [] and method == "GET":
        return ok({"locations": locations.list_locations()})
    if rest == [] and method == "POST":
        return created(locations.create_location(
            body.get("name"), address=body.get("address", ""),
            timezone=body.get("timezone", "UTC")))
    if rest == ["merge"] and method == "POST":
        return ok(locations.merge_locations(body["target_id"], body.get("source_ids", [])))
    if rest == ["match"] and method == "GET":
        return ok({"matches": locations.fuzzy_match((query or {}).get("name", ""))})
    if not rest:
        return None
    location_id = rest[0]
    if rest[1:] == [] and method == "GET":
        loc = locations.get_location(location_id)
        return ok(loc) if loc else not_found("Location not found")
    if rest[1:] == [] and method == "PUT":
        return ok(locations.update_location(location_id, body))
    if rest[1:] == [] and method == "DELETE":
        result = deletion.delete_location(
            location_id, cascade_events=(query or {}).get("cascade", "true") != "false")
        return ok(result) if result else not_found("Location not found")
    return None


def _admin_labels(method, rest, body):
    if not rest:
        return None
    taxonomy = _TAXONOMY.get(rest[0])
    if taxonomy is None:
        return bad_request(f"unknown label taxonomy: {rest[0]}")
    tail = rest[1:]
    if tail == [] and method == "GET":
        return ok({"labels": labels.list_labels(taxonomy)})
    if tail == [] and method == "POST":
        return created(labels.create_label(taxonomy, body.get("name")))
    if len(tail) == 1 and method == "PUT":
        return ok(labels.rename_label(taxonomy, tail[0], body.get("name")))
    if len(tail) == 1 and method == "DELETE":
        labels.delete_label(taxonomy, tail[0])
        return ok({"deleted": tail[0]})
    return None


def _route_admin(method, parts, query, body):
    resource = parts[1] if len(parts) > 1 else ""
    rest = parts[2:]

    if resource == "sources":
        return _admin_sources(method, rest, query, body)
    if resource == "events":
        return _admin_events(method, rest, query, body)
    if resource == "locations":
        return _admin_locations(method, rest, query, body)
    if resource == "labels":
        return _admin_labels(method, rest, body)
    if resource == "settings":
        if method == "GET":
            return ok(store.get_settings())
        if method == "PUT":
            return ok(store.put_settings(body))
    if resource == "notifications":
        if rest == [] and method == "GET":
            return ok({"notifications": notifications.list_notifications(
                unread_only=(query or {}).get("unread") == "true")})
        if len(rest) == 2 and rest[1] == "read" and method == "POST":
            return ok(notifications.mark_read(rest[0]))
    if resource == "deleted" and rest and method == "GET":
        entity = _DELETED_TYPES.get(rest[0])
        if entity is None:
            return bad_request(f"unknown entity type: {rest[0]}")
        return ok({"items": store.query_deleted(entity)})
    if resource == "restore" and method == "POST":
        result = deletion.restore(body["pk"], body["sk"])
        return ok(result) if result else not_found("Item not found")
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def route_request(event):
    method = event.get("httpMethod", "GET")
    if method == "OPTIONS":
        return _resp(200, "")

    parts = _segments(_route(event))
    query = event.get("queryStringParameters") or {}

    try:
        if parts and parts[0] == "public":
            response = _route_public(method, parts, query)
        elif parts and parts[0] == "admin":
            body = _body(event)
            # Stamp the reviewer's identity (from the Cognito authorizer claims)
            # so review feedback can be attributed without trusting the client.
            body.setdefault("_actor", _actor(event))
            response = _route_admin(method, parts, query, body)
        else:
            response = None
    except KeyError as exc:
        return bad_request(f"missing field: {exc}")
    except ValueError as exc:
        return bad_request(str(exc))

    return response if response is not None else not_found("Unknown endpoint")


def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event))
    try:
        return route_request(event)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return server_error(str(exc))
