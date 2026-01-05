import structlog

from src.services.workers.image_normalization_service import (
    create_worker_app,
    process_sqs_records,
)
from src.services.aws.s3 import S3Storage
from src.utils.config import AppConfig

logger = structlog.get_logger(__name__)


def handler(event, context):
    app = create_worker_app()
    region = AppConfig.AWS_REGION
    storage = S3Storage(bucket_name=AppConfig.S3_BUCKET_NAME, region=region)

    records = event.get("Records", [])
    with app.app_context():
        processed = process_sqs_records(records, storage)

    logger.info(
        "Image normalization Lambda run complete",
        processed=processed,
        aws_request_id=getattr(context, "aws_request_id", None),
    )
    return {"processed": processed}
