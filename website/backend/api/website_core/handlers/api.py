"""Website API Lambda — HTTP router over the website-core service layer.

Public endpoints (no auth) back the marketing site: `POST /api/intake` captures
scoped-quote requests, `POST /api/subscribe` adds newsletter signups. Admin
endpoints (`/api/admin/*`, behind the API Gateway Cognito authorizer) back the
submissions dashboard. Routing anchors on the "/api/" path segment so the one
Lambda serves the {proxy+} catch-all and any custom-domain base path alike.

This holds no business logic beyond request/response plumbing — it delegates to
the domain modules (intake, newsletter).
"""

import json
import logging
import os
from decimal import Decimal
from urllib.parse import unquote

from website_core.common import config
from website_core.common.errors import (
    ConfigError,
    UpstreamError,
    ValidationError,
)
from website_core.domain import intake
from website_core.domain import newsletter

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Serialization & responses
# ---------------------------------------------------------------------------

class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": config.allowed_origin(),
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Content-Type": "application/json",
    }


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": _cors_headers(),
        "body": json.dumps(body, cls=_DecimalEncoder),
    }


def ok(body):
    return _resp(200, body)


def created(body):
    return _resp(201, body)


def no_content():
    return {"statusCode": 204, "headers": _cors_headers(), "body": ""}


def bad_request(message):
    return _resp(400, {"error": message})


def not_found(message="Not found"):
    return _resp(404, {"error": message})


def server_error(message):
    return _resp(500, {"error": message})


def bad_gateway(message):
    return _resp(502, {"error": message})


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

def _method(event):
    ctx = (event.get("requestContext") or {}).get("http") or {}
    return event.get("httpMethod") or ctx.get("method") or "GET"


def _route(event):
    raw = event.get("path") or event.get("rawPath") or event.get("resource") or ""
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


def _query(event):
    return event.get("queryStringParameters") or {}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_public(method, parts, event):
    if parts == ["intake"] and method == "POST":
        item = intake.create_submission(_body(event), source_page=_body(event).get("source_page"))
        return created(item)
    if parts == ["subscribe"] and method == "POST":
        return created(newsletter.subscribe(_body(event)))
    return None


def _route_admin(method, rest, event):
    # rest is the path after "admin".
    if rest == ["submissions"] and method == "GET":
        query = _query(event)
        return ok(
            intake.list_submissions(
                limit=query.get("page_size", 50),
                cursor=query.get("cursor"),
            )
        )
    return None


def lambda_handler(event, _context=None):
    method = _method(event)
    if method == "OPTIONS":
        return no_content()

    parts = _segments(_route(event))

    try:
        if parts and parts[0] == "admin":
            response = _route_admin(method, parts[1:], event)
        else:
            response = _route_public(method, parts, event)
    except ValidationError as exc:
        return bad_request(str(exc))
    except UpstreamError as exc:
        logger.warning("Upstream error: %s", exc)
        return bad_gateway(str(exc))
    except ConfigError as exc:
        logger.error("Config error: %s", exc)
        return server_error(str(exc))
    except Exception:  # noqa: BLE001 — last-resort guard so we never leak a stack trace
        logger.exception("Unhandled error handling %s %s", method, parts)
        return server_error("Internal error")

    return response if response is not None else not_found()
