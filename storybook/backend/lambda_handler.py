"""
Lambda handler for running Flask app in AWS Lambda
This module adapts the Flask application to work with AWS Lambda.
Adds defensive logging so cold-start failures surface in CloudWatch.
"""
import logging

from mangum import Mangum
from mangum.adapters.wsgi import WSGIAdapter

from src.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

try:
    from src.app import app
    from src.config import Config
except Exception:
    # Emit the full stack trace to CloudWatch before re-raising so we can see
    # the real import/initialization failure instead of Mangum's generic error.
    logger.exception("Failed to initialize Flask app on cold start")
    raise

# Log high-level env info (no secrets) so we can confirm what the Lambda sees.
logger.info(
    "Cold start config",
    extra={
        "region": getattr(Config, "AWS_COGNITO_REGION", None),
        "bucket_set": bool(getattr(Config, "S3_BUCKET_NAME", None)),
        "db_url_set": bool(getattr(Config, "DATABASE_URL", None)),
        "db_name": getattr(Config, "DATABASE_NAME", None),
        "openai": bool(getattr(Config, "OPENAI_API_KEY", None)),
        "stability": bool(getattr(Config, "STABILITY_API_KEY", None)),
        "replicate": bool(getattr(Config, "REPLICATE_API_TOKEN", None)),
    },
)

# Wrap the Flask WSGI app so Mangum can treat it as ASGI.
asgi_app = WSGIAdapter(app)

# Mangum adapter for AWS Lambda
_mangum_handler = Mangum(asgi_app, lifespan="off")


def handler(event, context):
    """
    Entrypoint invoked by AWS Lambda. Wrap Mangum to log full errors.
    """
    http = event.get("requestContext", {}).get("http", {})
    path = event.get("rawPath") or event.get("path")
    method = http.get("method") or event.get("httpMethod")
    logger.info(
        "Handling request",
        extra={
            "path": path,
            "method": method,
            "aws_request_id": getattr(context, "aws_request_id", None),
        },
    )
    try:
        return _mangum_handler(event, context)
    except Exception:
        logger.exception(
            "Unhandled exception while processing Lambda event",
            extra={
                "path": path,
                "method": method,
                "aws_request_id": getattr(context, "aws_request_id", None),
            },
        )
        raise
