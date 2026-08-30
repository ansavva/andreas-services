"""Local consumer for this machine's callback queue. **Dev's half of the split.**

`dev-up.sh` runs this beside the Flask API, and it is the reason the receive and
process halves were separated at all. Replicate cannot reach
`http://localhost:8000`, so before this the webhook path could not run on a
developer's machine: local development fell back to polling and the code that
closes a run in production was code nobody had ever executed outside a unit test.

Now a real, signed Replicate callback reaches this machine's own API Gateway,
lands in this machine's own queue, and is processed **by the working tree** —
`services/callbacks.py`, the same module the prod worker Lambda drives.

    Replicate ──► studio-dev-<short12> API GW ──► receiver ──► SQS ──► this

Long-polling, so it is one held connection rather than a request a second: 20
seconds is the SQS maximum and the queue is empty almost all of the time.

**Its failures are not the API's.** A traceback here must not take the Flask
process down beside it, and a machine with no dev queue provisioned should say so
once and stop rather than crash-looping — `dev-up.sh` starts both, and a
developer who has not run `dev-aws-setup.sh` since this landed is the ordinary
case rather than an error.
"""

import json
import logging
import os
import signal
import sys

import boto3
from botocore.exceptions import ClientError

from studio_core.services import callbacks

logging.basicConfig(
    level=logging.INFO, format="[callbacks] %(message)s", stream=sys.stderr
)
logger = logging.getLogger(__name__)

#: The SQS maximum. Anything shorter is more requests for the same latency.
WAIT_SECONDS = 20

#: How many callbacks one receive may return. A batch is rare — a developer
#: submits runs one at a time — so this is about not leaving a second completion
#: waiting for a poll cycle behind a slow video download.
BATCH = 10

_running = True


def _stop(_signum, _frame):
    global _running
    _running = False


def drain(client, queue_url: str) -> int:
    """One long poll. Returns how many messages were handled."""
    received = client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=BATCH,
        WaitTimeSeconds=WAIT_SECONDS,
    )
    messages = received.get("Messages") or []
    for message in messages:
        try:
            run = callbacks.handle(message["Body"])
        except callbacks.Rejected as refusal:
            logger.error("dropping a callback: %s", refusal)
        except Exception:
            # Left on the queue deliberately: the visibility timeout brings it
            # back, and a developer who has just fixed the bug in their tree gets
            # the same callback delivered into the fix.
            logger.exception("callback failed; leaving it on the queue")
            continue
        else:
            if run is not None:
                logger.info("closed run %s as %s", run["id"], run["status"])
        client.delete_message(
            QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
        )
    return len(messages)


def main() -> int:
    queue_url = os.environ.get("STUDIO_CALLBACK_QUEUE_URL", "").strip()
    if not queue_url:
        logger.warning(
            "STUDIO_CALLBACK_QUEUE_URL is not set, so nothing will close a run "
            "when its generation finishes. Provision this machine's dev stack "
            "with ./studio/scripts/dev-aws-setup.sh, or close runs by hand with "
            "`studio runs reconcile <run>`."
        )
        return 0

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client = boto3.client("sqs")
    logger.info("watching %s", queue_url.rsplit("/", 1)[-1])
    while _running:
        try:
            drain(client, queue_url)
        except ClientError as exc:
            # A queue that does not exist is a stack that was destroyed, or a
            # machine id that moved. Said once, plainly, and then this stops —
            # a crash loop beside a working API is noise that hides the message.
            logger.error("cannot read the callback queue: %s", exc)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
