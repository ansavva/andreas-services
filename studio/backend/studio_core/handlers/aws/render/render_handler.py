"""AWS Lambda entrypoint for the render queue. **The second image.**

Every other handler in this tree runs the image the API is built from. This one
does not, and that is the whole decision the render-worker change turned on.

    studio-prod-api      Flask + Pillow, 512 MB, 60s   — every request
    studio-prod-render   + ffmpeg, 4 GB, 10 min, 10 GB /tmp — a cut

`ffmpeg` through `imageio-ffmpeg` is ~80 MB. Putting it in the API image would
have charged every folder listing for it, and putting the *work* in the API
would have put a multi-minute encode behind API Gateway's 30-second ceiling. So
there are two images, two ECR repositories and two build steps in
`studio-prod.yaml` — and `Dockerfile.render` is a three-line delta on
`Dockerfile`, installing one extra Poetry group, so the two cannot drift in
anything but that group.

**`batchItemFailures` rather than raising**, exactly as `handlers/aws/worker`
does and for the same reason: a batch is several jobs for several callers, and
letting one exception escape redrives all of them. Partial batch response tells
SQS precisely which message to keep. The batch size is 1 here rather than 10
(see `modules/render`) — a stitch is minutes, so batching would serialise
unrelated jobs behind each other under one timeout — but the mechanism stays,
because a batch size is a tuning value and losing correctness to it would not be.
"""

import logging

from studio_core.services import render

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def handler(event, _context):
    """Drain one SQS batch. Anything not reported as a failure is deleted."""
    failures = []
    for record in event.get("Records") or []:
        message_id = record.get("messageId")
        try:
            render.handle(record.get("body") or "")
        except render.RenderError as refusal:
            # Deliberately NOT a failure. `services/render.run` already closed
            # the job row `failed`; what reaches here is a message that names no
            # job at all — malformed, or about a render that was deleted with its
            # library. Redriving it only fills the dead-letter queue with
            # something nobody can act on.
            logger.error("Dropping a render message: %s", refusal)
        except Exception:
            # Everything else is transient by assumption: DynamoDB throttled, S3
            # refused a read, the container ran out of time. Let SQS bring it
            # back, and let the DLQ catch what never stops failing. `run` leaves
            # the row `running` in this case, which is what a poller should see.
            logger.exception("Render %s failed; leaving it on the queue", message_id)
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
