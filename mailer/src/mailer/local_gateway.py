from __future__ import annotations

import hashlib
import logging
import os
import queue
import secrets
import smtplib
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import Flask, jsonify, request

from mailer.config import ServiceConfig, load_service_registry
from mailer.errors import ConflictError, MailerError, ValidationError
from mailer.mime import AttachmentContent, build_message
from mailer.models import MAX_REQUEST_BYTES, AttachmentUploadRequest, MessageRequest

if os.environ.get("MAILER_ENVIRONMENT", "local").lower() != "local":
    raise RuntimeError("the local Mailer gateway refuses to run outside MAILER_ENVIRONMENT=local")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("mailer.local")
app = Flask(__name__)


@dataclass
class LocalUpload:
    service_id: str
    attachment_id: str
    token: str
    request: AttachmentUploadRequest
    expires_at: datetime
    data: bytes | None = None


@dataclass(frozen=True)
class LocalDelivery:
    service: ServiceConfig
    request: MessageRequest
    attachments: list[AttachmentContent]


class LocalState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.uploads: dict[str, LocalUpload] = {}
        self.messages: dict[str, str] = {}
        self.deliveries: queue.Queue[LocalDelivery] = queue.Queue()

    def register_upload(
        self, service_id: str, upload_request: AttachmentUploadRequest
    ) -> LocalUpload:
        attachment_id = f"att_{secrets.token_urlsafe(18)}"
        token = secrets.token_urlsafe(32)
        upload = LocalUpload(
            service_id=service_id,
            attachment_id=attachment_id,
            token=token,
            request=upload_request,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        with self.lock:
            self.uploads[token] = upload
        return upload

    def put_upload(self, token: str, data: bytes, content_type: str, checksum: str) -> None:
        with self.lock:
            upload = self.uploads.get(token)
            if not upload or upload.expires_at < datetime.now(UTC):
                raise ValidationError("upload URL is invalid or expired")
            if content_type != upload.request.content_type:
                raise ValidationError("content-type does not match upload registration")
            if len(data) != upload.request.size_bytes:
                raise ValidationError("uploaded size does not match upload registration")
            actual = hashlib.sha256(data).hexdigest()
            if actual != upload.request.sha256 or checksum != actual:
                raise ValidationError("uploaded checksum does not match upload registration")
            upload.data = data

    def attachments_for(
        self, service_id: str, message: MessageRequest
    ) -> list[AttachmentContent]:
        result: list[AttachmentContent] = []
        with self.lock:
            candidates = list(self.uploads.values())
            for reference in message.attachments:
                upload = next(
                    (
                        item
                        for item in candidates
                        if item.attachment_id == reference.attachment_id
                        and item.service_id == service_id
                        and item.request.application_message_id
                        == message.application_message_id
                    ),
                    None,
                )
                if not upload or upload.data is None:
                    raise ValidationError("attachment upload is missing or incomplete")
                result.append(
                    AttachmentContent(
                        attachment_id=reference.attachment_id,
                        file_name=upload.request.file_name,
                        content_type=upload.request.content_type,
                        disposition=reference.disposition,
                        content_id=reference.content_id,
                        data=upload.data,
                    )
                )
        return result

    def admit(self, service: ServiceConfig, message: MessageRequest) -> None:
        message_key = f"{service.service_id}#{message.application_message_id}"
        request_hash = message.canonical_hash()
        attachments = self.attachments_for(service.service_id, message)
        with self.lock:
            existing = self.messages.get(message_key)
            if existing and existing != request_hash:
                raise ConflictError("application_message_id was reused with different content")
            if existing:
                return
            self.messages[message_key] = request_hash
        self.deliveries.put(LocalDelivery(service, message, attachments))


state = LocalState()
services = load_service_registry(local=True)


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


def _delivery_worker() -> None:
    smtp_host = os.environ.get("MAILER_SMTP_HOST", "mailpit")
    smtp_port = int(os.environ.get("MAILER_SMTP_PORT", "1025"))
    while True:
        delivery = state.deliveries.get()
        try:
            message = build_message(delivery.service, delivery.request, delivery.attachments)
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
                smtp.send_message(message)
            logger.info(
                "local email captured service_id=%s application_message_id=%s category=%s",
                delivery.service.service_id,
                delivery.request.application_message_id,
                delivery.request.category,
            )
        except Exception:
            logger.exception(
                "local email capture failed service_id=%s application_message_id=%s",
                delivery.service.service_id,
                delivery.request.application_message_id,
            )
        finally:
            state.deliveries.task_done()


threading.Thread(target=_delivery_worker, name="mailer-local-delivery", daemon=True).start()
