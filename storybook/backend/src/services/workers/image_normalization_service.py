import json
import uuid
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, Iterable

import structlog
from dotenv import load_dotenv
from flask import Flask
from werkzeug.datastructures import FileStorage
import time

from src.utils.config import AppConfig
from src.services.aws.s3 import S3Storage
from src.repositories.db.database import get_db, init_db
from src.repositories.db.image_repo import ImageRepo
from src.services.workers.image_normalization_logic import convert_heic_if_needed, resize_image

load_dotenv()
logger = structlog.get_logger(__name__)

def create_worker_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(AppConfig)
    init_db(app)
    return app


def _build_destination_key(user_id: str, project_id: str, image_id: str, filename: str) -> str:
    safe_filename = filename.replace("/", "_")
    return f"users/{user_id}/projects/{project_id}/images/{image_id}_{safe_filename}"


def _build_temp_upload_key(user_id: str, project_id: str, image_id: str, filename: str) -> str:
    safe_filename = filename.replace("/", "_")
    return f"temp/uploads/{user_id}/{project_id}/{image_id}_{safe_filename}"


def _require_field(payload: Dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    if value in (None, ""):
        raise ValueError(f"Missing required field: {key}")
    return value


def _parse_body(body: Any) -> Dict[str, Any]:
    if body is None:
        raise ValueError("Missing message body")
    if isinstance(body, dict):
        return body
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")
    if isinstance(body, str):
        return json.loads(body)
    raise ValueError(f"Unsupported message body type: {type(body)}")


def process_message(payload: Dict[str, Any], storage: S3Storage) -> Dict[str, Any]:
    time.sleep(60)
    image_id = _require_field(payload, "image_id")
    resize_flag = payload.get("resize", True)
    if isinstance(resize_flag, str):
        resize_flag = resize_flag.strip().lower() not in ("false", "0", "no")
    resize_flag = bool(resize_flag)

    image_repo = ImageRepo()
    image = image_repo.get_image_any_user(image_id)

    user_id = image.user_id
    project_id = image.project_id
    filename = image.filename
    content_type = image.content_type or "application/octet-stream"
    image_type = image.image_type or "training"
    source_key = _build_temp_upload_key(
        user_id=user_id,
        project_id=str(project_id),
        image_id=image_id,
        filename=filename,
    )

    destination_key = image.s3_key or _build_destination_key(
        user_id=user_id,
        project_id=str(project_id),
        image_id=image_id,
        filename=filename,
    )

    file_bytes = storage.download_file(source_key)
    if file_bytes is None:
        raise ValueError(f"Source key not found: {source_key}")

    file_stream = BytesIO(file_bytes)
    file_stream.seek(0)
    file_obj = FileStorage(
        stream=file_stream,
        filename=filename,
        content_type=content_type,
    )
    file_obj.headers["Content-Length"] = str(len(file_bytes))

    if resize_flag:
        file_obj, filename = resize_image(file_obj, filename)
    else:
        file_obj, filename = convert_heic_if_needed(file_obj, filename)
        destination_key = _build_destination_key(
            user_id=user_id,
            project_id=str(project_id),
            image_id=image_id,
            filename=filename,
        )

    size_bytes = file_obj.content_length
    if not size_bytes:
        try:
            if hasattr(file_obj.stream, "getvalue"):
                size_bytes = len(file_obj.stream.getvalue())
        except ValueError:
            size_bytes = len(file_bytes)

    storage.upload_file(file_obj, destination_key)

    db = get_db()
    db.images.update_one(
        {"_id": image_id, "user_id": user_id},
        {
            "$set": {
                "project_id": str(project_id),
                "s3_key": destination_key,
                "filename": filename,
                "content_type": file_obj.content_type or "application/octet-stream",
                "size_bytes": size_bytes or 0,
                "image_type": image_type,
                "processing": False,
            },
            "$setOnInsert": {"created_at": datetime.utcnow()},
        },
        upsert=True,
    )

    storage.delete_file(source_key)

    return {
        "image_id": image_id,
        "s3_key": destination_key,
        "filename": filename,
    }


def process_sqs_records(records: Iterable[Dict[str, Any]], storage: S3Storage) -> int:
    processed = 0
    for record in records:
        payload = _parse_body(record.get("Body") or record.get("body"))
        result = process_message(payload, storage)
        logger.info("Processed image normalization job", **result)
        processed += 1
    return processed


__all__ = ["create_worker_app", "process_message", "process_sqs_records"]
