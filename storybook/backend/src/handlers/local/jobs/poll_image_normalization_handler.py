import os
import sys
import time

import structlog

from src.services.aws.s3 import S3Storage
from src.services.aws.sqs import SqsClient
from src.services.workers.image_normalization_service import (
    create_worker_app,
    process_sqs_records,
)
from src.utils.config import AppConfig

logger = structlog.get_logger(__name__)


def _require_env(name: str) -> None:
    if not os.getenv(name):
        raise ValueError(f"{name} must be set")


def run() -> None:
    _require_env("IMAGE_UPLOAD_QUEUE_URL")
    os.environ.setdefault("IMAGE_WORKER_MAX_MESSAGES", "1")
    os.environ.setdefault("IMAGE_WORKER_WAIT_SECONDS", "20")

    queue_url = os.getenv("IMAGE_UPLOAD_QUEUE_URL")
    region = AppConfig.AWS_REGION
    max_messages = int(os.getenv("IMAGE_WORKER_MAX_MESSAGES", "1"))
    wait_seconds = int(os.getenv("IMAGE_WORKER_WAIT_SECONDS", "20"))
    sleep_seconds = float(os.getenv("IMAGE_WORKER_IDLE_SLEEP", "2"))

    sqs = SqsClient(region=region)
    storage = S3Storage(bucket_name=AppConfig.S3_BUCKET_NAME, region=region)

    logger.info(
        "Starting SQS image normalization worker",
        queue_url=queue_url,
        region=region,
        max_messages=max_messages,
        wait_seconds=wait_seconds,
    )

    app = create_worker_app()
    with app.app_context():
        while True:
            messages = sqs.receive_messages(
                queue_url=queue_url,
                max_messages=max_messages,
                wait_seconds=wait_seconds,
            )
            if not messages:
                time.sleep(sleep_seconds)
                if os.getenv("IMAGE_WORKER_RUN_ONCE") == "true":
                    break
                continue

            for message in messages:
                receipt_handle = message["ReceiptHandle"]
                try:
                    process_sqs_records([message], storage)
                except Exception:
                    logger.exception("Failed to process message", message_id=message.get("MessageId"))
                    continue
                sqs.delete_message(queue_url=queue_url, receipt_handle=receipt_handle)

            if os.getenv("IMAGE_WORKER_RUN_ONCE") == "true":
                break


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"Image normalization worker failed: {exc}")
        sys.exit(1)
