"""
Lambda handler for running Flask app in AWS Lambda
This module adapts the Flask application to work with AWS Lambda.
Adds defensive logging so cold-start failures surface in CloudWatch.
"""
import logging
import os

from mangum import Mangum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
    "Cold start config: region=%s bucket_set=%s db_url_set=%s db_name=%s openai=%s stability=%s replicate=%s",
    getattr(Config, "AWS_COGNITO_REGION", None),
    bool(getattr(Config, "S3_BUCKET_NAME", None)),
    bool(getattr(Config, "DATABASE_URL", None)),
    getattr(Config, "DATABASE_NAME", None),
    bool(getattr(Config, "OPENAI_API_KEY", None)),
    bool(getattr(Config, "STABILITY_API_KEY", None)),
    bool(getattr(Config, "REPLICATE_API_TOKEN", None)),
)

# Mangum adapter for AWS Lambda
_mangum_handler = Mangum(app, lifespan="off")


def handler(event, context):
    """
    Entrypoint invoked by AWS Lambda. Wrap Mangum to log full errors.
    """
    http = event.get("requestContext", {}).get("http", {})
    path = event.get("rawPath") or event.get("path")
    method = http.get("method") or event.get("httpMethod")
    logger.info("Handling request path=%s method=%s", path, method)
    try:
        return _mangum_handler(event, context)
    except Exception:
        logger.exception("Unhandled exception while processing Lambda event")
        raise
