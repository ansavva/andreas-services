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
from datetime import date
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DYNAMODB_TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
DYNAMODB_EMAILS_TABLE_NAME = os.environ["DYNAMODB_EMAILS_TABLE_NAME"]

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE_NAME)
emails_table = dynamodb.Table(DYNAMODB_EMAILS_TABLE_NAME)

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
                DYNAMODB_EMAILS_TABLE_NAME: {"Keys": batch}
            }
        )
        for item in response.get("Responses", {}).get(DYNAMODB_EMAILS_TABLE_NAME, []):
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


def get_all_events(upcoming_only=False):
    """Scan scout-events, join email metadata, and return all events."""
    today = date.today().isoformat()

    if upcoming_only:
        result = table.scan(FilterExpression=Attr("date").gte(today))
    else:
        result = table.scan()

    items = result.get("Items", [])

    while "LastEvaluatedKey" in result:
        kwargs = {"ExclusiveStartKey": result["LastEvaluatedKey"]}
        if upcoming_only:
            kwargs["FilterExpression"] = Attr("date").gte(today)
        result = table.scan(**kwargs)
        items.extend(result.get("Items", []))

    unique_email_ids = {item["email_id"] for item in items if item.get("email_id")}
    email_map = _fetch_email_data(unique_email_ids)

    events = [_merge_email_fields(item, email_map) for item in items]
    return sort_events(events)


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
# Request routing
# ---------------------------------------------------------------------------

def route_request(http_method, resource, path_params, query_params):
    """Dispatch to the appropriate handler based on method and resource template."""
    if http_method == "OPTIONS":
        return cors_preflight()

    if http_method == "GET":
        if resource == "/api/events":
            upcoming = (query_params or {}).get("upcoming", "").lower() == "true"
            events = get_all_events(upcoming_only=upcoming)
            return ok({"events": events, "count": len(events)})

        if resource == "/api/events/{id}":
            event_id = (path_params or {}).get("id", "")
            if not event_id:
                return bad_request("Missing event ID")
            event = get_event_by_id(event_id)
            if event is None:
                return not_found(f"Event {event_id!r} not found")
            return ok(event)

        if resource == "/api/admin/emails":
            emails = get_all_emails()
            return ok({"emails": emails, "count": len(emails)})

    return not_found("Unknown endpoint")


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event))

    try:
        http_method = event.get("httpMethod", "GET")
        # Use `resource` (the API Gateway resource template) rather than `path`
        # because API Gateway does not strip the custom-domain base path from
        # `event["path"]` — e.g. via scout-api-pr.andreas.services/33/api/events
        # the path arrives as "/33/api/events" while resource is always "/api/events".
        resource = event.get("resource") or event.get("path", "/api/events")
        path_params = event.get("pathParameters") or {}
        query_params = event.get("queryStringParameters") or {}
        return route_request(http_method, resource, path_params, query_params)

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return server_error(str(exc))
