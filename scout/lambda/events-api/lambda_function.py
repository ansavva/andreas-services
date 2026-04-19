"""
Events API Lambda Function

Serves a REST API via API Gateway for querying NYC events stored in DynamoDB.

Endpoints:
  GET  /api/events          - List events (optional ?upcoming=true filter)
  GET  /api/events/{id}     - Get a single event by event_id
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

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

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


def get_all_events(upcoming_only=False):
    """Scan the DynamoDB table and return all events, optionally filtering to upcoming."""
    today = date.today().isoformat()

    if upcoming_only:
        result = table.scan(
            FilterExpression=Attr("date").gte(today),
        )
    else:
        result = table.scan()

    items = result.get("Items", [])

    # Handle DynamoDB pagination
    while "LastEvaluatedKey" in result:
        result = table.scan(
            ExclusiveStartKey=result["LastEvaluatedKey"],
            FilterExpression=Attr("date").gte(today) if upcoming_only else None,
        )
        items.extend(result.get("Items", []))

    return sort_events(items)


def get_event_by_id(event_id):
    """Retrieve a single event by its primary key."""
    result = table.get_item(Key={"event_id": event_id})
    return result.get("Item")


# ---------------------------------------------------------------------------
# Request routing
# ---------------------------------------------------------------------------

def route_request(http_method, path, query_params):
    """Dispatch to the appropriate handler based on method and path."""
    if http_method == "OPTIONS":
        return cors_preflight()

    # Collapse double slashes but preserve trailing slash (trailing slash = missing event ID)
    while "//" in path:
        path = path.replace("//", "/")

    if http_method == "GET":
        if path == "/api/events":
            upcoming = (query_params or {}).get("upcoming", "").lower() == "true"
            events = get_all_events(upcoming_only=upcoming)
            return ok({"events": events, "count": len(events)})

        if path.startswith("/api/events/"):
            event_id = path[len("/api/events/"):]
            if not event_id:
                return bad_request("Missing event ID")
            event = get_event_by_id(event_id)
            if event is None:
                return not_found(f"Event {event_id!r} not found")
            return ok(event)

    return not_found("Unknown endpoint")


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event))

    try:
        http_method = event.get("httpMethod", "GET")
        path = event.get("path", "/api/events")
        query_params = event.get("queryStringParameters") or {}
        return route_request(http_method, path, query_params)

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return server_error(str(exc))
