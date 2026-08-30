"""AWS Lambda entrypoint for the callback queue. **Prod's consumer.**

The same image the API runs, with a different command — so the code that closes a
run is the code that was built, tested and reviewed with everything else, and
there is no second artifact to keep in step.

Its Lambda is sized for what it actually does, which is why it is a function of
its own rather than a second event source on the API's: it downloads a model
output and puts it in the bucket, so it wants 2 GB and a real ephemeral disk and
minutes of wall clock. The API Lambda answers listings in milliseconds and is
untouched at 512 MB and 60 seconds. One function sized for the worst case would
have charged every folder listing for the largest video studio can produce.

**`batchItemFailures` rather than raising.** A batch is up to ten callbacks for
ten different runs; letting one exception escape redrives all ten, so nine runs
that closed correctly are closed again — harmless, because
`generate.close_from_prediction` is idempotent, and wasteful, because each retry
re-downloads nothing but still wakes 2 GB of Lambda. Partial batch response tells
SQS exactly which message to keep.
"""

import logging

from studio_core.services import callbacks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def handler(event, _context):
    """Drain one SQS batch. Anything not reported as a failure is deleted."""
    failures = []
    for record in event.get("Records") or []:
        message_id = record.get("messageId")
        try:
            callbacks.handle(record.get("body") or "")
        except callbacks.Rejected as refusal:
            # Deliberately NOT a failure. A rejected message is one that will
            # never succeed — a signature that does not match, a run that no
            # longer exists — and redriving it only fills the dead-letter queue
            # with something nobody can act on. Logged at error, and dropped.
            logger.error("Dropping a callback: %s", refusal)
        except Exception:
            # Everything else is transient by assumption: the provider was
            # unreachable, S3 refused a write, DynamoDB throttled. Let SQS bring
            # it back, and let the DLQ catch what never stops failing.
            logger.exception("Callback %s failed; leaving it on the queue", message_id)
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
