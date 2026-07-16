from __future__ import annotations

import base64
import json
import logging
from typing import Any

from mailer.production.auth import authorize, principal_from_event
from mailer.production.config import load_service_registry
from mailer.production.store import AwsStore
from mailer.shared.errors import (
    AuthorizationError,
    ConflictError,
    MailerError,
    RetryableError,
    ValidationError,
)
from mailer.shared.models import MAX_REQUEST_BYTES, AttachmentUploadRequest, MessageRequest

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or ""
    data = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode()
    if len(data) > MAX_REQUEST_BYTES:
        raise ValidationError("request exceeds 4 MiB")
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValidationError("request body must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("request body must be a JSON object")
    return parsed


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        path = event.get("rawPath") or event.get("path", "")
        service_id = event.get("pathParameters", {}).get("service_id")
        registry = load_service_registry()
        service = registry.get(service_id)
        if not service:
            raise AuthorizationError("service route is not registered")
        authorize(service, principal_from_event(event))
        store = AwsStore()

        if path.endswith("/attachment-uploads"):
            upload = AttachmentUploadRequest.from_dict(_body(event))
            return _response(201, store.register_attachment(service, upload))
        if path.endswith("/messages"):
            message = MessageRequest.from_dict(_body(event), service)
            store.admit_message(service, message)
            return _response(
                202,
                {
                    "schema_version": 1,
                    "application_message_id": message.application_message_id,
                    "status": "accepted",
                },
            )
        return _response(404, {"error": "NotFound", "message": "route not found"})
    except AuthorizationError as exc:
        return _response(403, {"error": "Forbidden", "message": str(exc)})
    except ConflictError as exc:
        return _response(409, {"error": "Conflict", "message": str(exc)})
    except ValidationError as exc:
        return _response(400, {"error": "ValidationError", "message": str(exc)})
    except RetryableError:
        logger.exception("retryable Mailer admission failure")
        return _response(503, {"error": "Unavailable", "message": "admission is unavailable"})
    except MailerError as exc:
        return _response(400, {"error": exc.__class__.__name__, "message": str(exc)})
    except Exception:
        logger.exception("unexpected Mailer admission failure")
        return _response(500, {"error": "InternalError", "message": "admission failed"})
