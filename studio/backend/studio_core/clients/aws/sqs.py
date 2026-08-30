"""Thin boto3 wrapper over SQS, for putting a render job on the queue.

**One verb, and it is a send.** Nothing in this process reads a queue: in prod
the render worker and the callback worker are both driven by an event source
mapping, and in dev the drain is `handlers/local/consumer`, which builds its own
client because it long-polls with parameters no shared wrapper should have an
opinion about.

Shaped like `clients/aws/ssm.py` — lazily built, module-cached, `reset_client`
for the tests — so a reader who knows one knows all four clients in this package.
"""

import logging

import boto3
from botocore.exceptions import ClientError

from studio_core import config
from studio_core.errors import UpstreamError

logger = logging.getLogger(__name__)

_client = None


def client():
    """Lazily built, module-cached SQS client."""
    global _client
    if _client is None:
        _client = boto3.client("sqs", region_name=config.aws_region())
    return _client


def reset_client():
    """Drop the cached client. For tests, which stand a new moto queue up per case."""
    global _client
    _client = None


def send(queue_url: str, body: str) -> str:
    """Put one message on a queue. -> its `MessageId`.

    The failure is an `UpstreamError` rather than a bare `ClientError` so it maps
    to 502 the way every other AWS failure in this service does — and so the
    caller can tell "the queue refused this" from "the job was rejected", which
    are a retry and a fix respectively.
    """
    try:
        response = client().send_message(QueueUrl=queue_url, MessageBody=body)
    except ClientError as exc:
        logger.warning("SendMessage failed for %s: %s", queue_url, exc)
        raise UpstreamError("Could not reach the queue") from exc
    return response.get("MessageId", "")
