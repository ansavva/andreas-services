"""The long-poll loop both local consumers run. **Dev's half of two splits.**

There are two queues in a per-machine dev stack now — the callback queue, which
carries a finished Replicate prediction, and the render queue, which carries a
stitch or a frame grab. Prod drains each with a Lambda on an event source
mapping; dev drains both with a process beside `dev-up.sh`, so that the code
which closes a run and the code which cuts a scene are **the working tree** and
not something first executed in production.

This module is the loop they share. It was written once, inside
`callback_consumer.py`, and moved here when the render queue arrived rather than
copied: the two consumers differ in a queue URL, a handler and a log prefix, and
a hundred duplicated lines of receive/delete/signal handling would have been a
hundred lines to keep in step for no gain.

What each caller keeps for itself is the part that is genuinely different: which
exception means *drop this message* rather than *leave it on the queue*.
"""

import logging
import os
import signal
import sys
from typing import Callable

import boto3
from botocore.exceptions import ClientError

#: The SQS maximum. Anything shorter is more requests for the same latency.
WAIT_SECONDS = 20

_running = True


def _stop(_signum, _frame):
    global _running
    _running = False


def logger_for(name: str) -> logging.Logger:
    """A logger whose lines say which consumer wrote them.

    Both of these run in one terminal beside a Flask dev server, so an
    unprefixed line is a line nobody can attribute.
    """
    logging.basicConfig(level=logging.INFO, format=f"[{name}] %(message)s", stream=sys.stderr)
    return logging.getLogger(f"studio.consumer.{name}")


def drain(client, queue_url: str, *, batch: int, handle: Callable[[str], None],
          droppable: type[Exception], log: logging.Logger) -> int:
    """One long poll. Returns how many messages were handled.

    A message that raises `droppable` is deleted — it will never succeed, and
    redriving it only fills the dead-letter queue with something nobody can act
    on. Anything else is left on the queue deliberately: the visibility timeout
    brings it back, and a developer who has just fixed the bug in their tree gets
    the same message delivered into the fix.
    """
    received = client.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=batch, WaitTimeSeconds=WAIT_SECONDS)
    messages = received.get("Messages") or []
    for message in messages:
        try:
            handle(message["Body"])
        except droppable as refusal:
            log.error("dropping a message: %s", refusal)
        except Exception:
            log.exception("failed; leaving it on the queue")
            continue
        client.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
    return len(messages)


def serve(name: str, queue_variable: str, unset_advice: str, *, batch: int,
          handle: Callable[[str], None], droppable: type[Exception]) -> int:
    """Poll one queue until interrupted. The whole of a local consumer's `main`.

    **An unset queue variable is a warning and a clean exit, not a crash.**
    `dev-up.sh` starts these unconditionally, and a machine whose dev stack
    predates the queue is the ordinary case rather than an error — so it says
    what to run and stops, instead of crash-looping beside a working API.
    """
    log = logger_for(name)
    queue_url = os.environ.get(queue_variable, "").strip()
    if not queue_url:
        log.warning("%s is not set. %s", queue_variable, unset_advice)
        return 0

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client = boto3.client("sqs")
    log.info("watching %s", queue_url.rsplit("/", 1)[-1])
    while _running:
        try:
            drain(client, queue_url, batch=batch, handle=handle, droppable=droppable, log=log)
        except ClientError as exc:
            # A queue that does not exist is a stack that was destroyed, or a
            # machine id that moved. Said once, plainly, and then this stops — a
            # crash loop beside a working API is noise that hides the message.
            log.error("cannot read the queue: %s", exc)
            return 1
    return 0
