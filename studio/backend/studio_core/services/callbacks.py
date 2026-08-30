"""Processing one queued callback. **The consumer, and there is only one.**

`handlers/aws/hook` receives a callback and enqueues it without looking at it.
This is what looks at it: verify the signature, find the run, close it. Two
things drive this module and neither has any logic of its own —

| Driver | Where it runs |
|---|---|
| `handlers/aws/worker` | prod, on an SQS event source mapping |
| `handlers/local/consumer` | a developer's laptop, long-polling this machine's queue |

— which is the whole point of splitting receive from process. Before this, the
callback closed the run inline in the API Lambda, so the webhook path could not
run locally at all: Replicate cannot reach `localhost`, and the fallback was to
poll. The code that closes a run in production was therefore code no developer
had ever executed. It is the working tree now, against a real signed callback.

## The signature is checked here, not at the edge

The receiver is a dependency-free zip Lambda with no credential and no HTTP
client, packaged straight from the repo so that the **per-machine dev
environment** can afford one. Verification needs Replicate's per-account webhook
secret, which needs both. So the raw bytes are carried through base64-encoded and
checked here — in the module both consumers share, so there is one
implementation, and it is one that actually runs in development.

A message that fails verification is **dropped, not retried**. A bad signature is
not a transient condition: the same bytes will fail the same way forever, and
retrying them to a dead-letter queue would fill it with other people's noise. A
genuine failure — the provider unreachable, S3 refusing a write — raises, and
SQS redrives it.
"""

import base64
import binascii
import json
import logging

from studio_core import config
from studio_core.clients import replicate
from studio_core.errors import NotFoundError
from studio_core.services import catalog, generate

logger = logging.getLogger(__name__)


class Rejected(Exception):
    """The message will never succeed. Delete it rather than redriving it."""


def _decode(message: dict) -> tuple[str, dict, bytes]:
    run_id = message.get("run") or ""
    if not run_id.startswith("run-"):
        raise Rejected(f"message names no run ({run_id!r})")
    headers = message.get("headers") or {}
    try:
        body = base64.b64decode(message.get("body_b64") or "")
    except (ValueError, binascii.Error) as exc:
        raise Rejected(f"message body is not base64: {exc}") from exc
    return run_id, headers, body


def process(message: dict) -> dict | None:
    """Verify one queued callback and close the run it reports on.

    Returns the updated run, or `None` when the message was rejected — the
    difference the callers act on is not the return value but the exception:
    `Rejected` means delete, anything else means let the queue try again.

    **Idempotent all the way down.** `generate.close_from_prediction` returns a
    terminal run untouched, so at-least-once delivery is ordinary traffic rather
    than a hazard — which is what lets the receiver ack before anything has been
    verified, and what lets a redrive be safe.
    """
    run_id, headers, body = _decode(message)

    try:
        replicate.verify_webhook(
            replicate.webhook_secret(),
            headers.get("webhook-id", ""),
            headers.get("webhook-timestamp", ""),
            headers.get("webhook-signature", ""),
            body,
            config.webhook_tolerance_seconds(),
        )
    except ValueError as refusal:
        raise Rejected(f"callback for {run_id} failed verification: {refusal}") from refusal

    try:
        prediction = json.loads(body)
    except json.JSONDecodeError as exc:
        raise Rejected(f"callback for {run_id} is not JSON: {exc}") from exc
    if not isinstance(prediction, dict):
        raise Rejected(f"callback for {run_id} is not a JSON object")

    try:
        record = catalog.entity(catalog.ENTITY_RUN, run_id)
    except NotFoundError as exc:
        # Verified, and about a run this library does not have. A deleted run is
        # the ordinary way to reach this; there is nothing to retry toward.
        raise Rejected(f"callback names run {run_id}, which does not exist") from exc

    reported = prediction.get("id")
    if reported and record.get("prediction_id") and reported != record["prediction_id"]:
        # The signature held, so this really is the provider — and applying it
        # would close a run with another prediction's output.
        raise Rejected(
            f"callback for {run_id} names prediction {reported}, "
            f"not {record['prediction_id']}"
        )

    return generate.close_from_prediction(record, prediction)


def handle(raw_body: str) -> dict | None:
    """One SQS message body, as the string both drivers receive it as."""
    try:
        message = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise Rejected(f"queue message is not JSON: {exc}") from exc
    if not isinstance(message, dict):
        raise Rejected("queue message is not a JSON object")
    return process(message)
