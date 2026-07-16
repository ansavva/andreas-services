from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, request

from mailer.local.config import load_service_registry
from mailer.local.mailpit import MailpitTransport
from mailer.local.state import LocalState
from mailer.local.worker import LocalDeliveryWorker
from mailer.shared.config import ServiceConfig
from mailer.shared.errors import ConflictError, MailerError, ValidationError
from mailer.shared.models import MAX_REQUEST_BYTES, AttachmentUploadRequest, MessageRequest

if os.environ.get("MAILER_ENVIRONMENT", "local").lower() != "local":
    raise RuntimeError("the local Mailer API refuses to run outside MAILER_ENVIRONMENT=local")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
app = Flask(__name__)
state = LocalState()
services = load_service_registry()


def _service(service_id: str) -> ServiceConfig:
    service = services.get(service_id)
    if not service:
        raise ValidationError("service is not registered in the local Mailer")
    return service


def _json_body() -> dict:
    if request.content_length and request.content_length > MAX_REQUEST_BYTES:
        raise ValidationError("request exceeds 4 MiB")
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValidationError("request body must be a JSON object")
    return value


@app.errorhandler(MailerError)
def expected_error(error: MailerError):
    status = 409 if isinstance(error, ConflictError) else 400
    return jsonify({"error": error.__class__.__name__, "message": str(error)}), status


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/v1/services/<service_id>/attachment-uploads")
def attachment_upload(service_id: str):
    _service(service_id)
    upload_request = AttachmentUploadRequest.from_dict(_json_body())
    upload = state.register_upload(service_id, upload_request)
    base_url = request.host_url.rstrip("/")
    return (
        jsonify(
            {
                "schema_version": 1,
                "attachment_id": upload.attachment_id,
                "upload_url": f"{base_url}/v1/local-uploads/{upload.token}",
                "required_headers": {
                    "content-type": upload.request.content_type,
                    "x-mailer-content-sha256": upload.request.sha256,
                },
                "expires_at": upload.expires_at.isoformat().replace("+00:00", "Z"),
            }
        ),
        201,
    )


@app.put("/v1/local-uploads/<token>")
def put_upload(token: str):
    state.put_upload(
        token,
        request.get_data(cache=False),
        request.headers.get("content-type", ""),
        request.headers.get("x-mailer-content-sha256", ""),
    )
    return "", 204


@app.post("/v1/services/<service_id>/messages")
def submit_message(service_id: str):
    service = _service(service_id)
    message = MessageRequest.from_dict(_json_body(), service)
    state.admit(service, message)
    return (
        jsonify(
            {
                "schema_version": 1,
                "application_message_id": message.application_message_id,
                "status": "accepted",
            }
        ),
        202,
    )


LocalDeliveryWorker(state.deliveries, MailpitTransport()).start()
