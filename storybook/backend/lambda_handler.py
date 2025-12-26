"""
Lambda handler for running Flask app in AWS Lambda
This module adapts the Flask application to work with AWS Lambda.
Adds defensive logging so cold-start failures surface in CloudWatch.
"""
import logging
import traceback

from mangum import Mangum

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    from src.app import app
except Exception as exc:
    # Emit the full stack trace to CloudWatch before re-raising so we can see
    # the real import/initialization failure instead of Mangum's generic error.
    logger.exception("Failed to initialize Flask app on cold start")
    raise

# Mangum adapter for AWS Lambda
handler = Mangum(app, lifespan="off")
