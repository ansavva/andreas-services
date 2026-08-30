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

**The poll loop moved to `consumer/poll.py`** when the render queue arrived:
there are two of these now, and they differ in a queue URL, a handler and
which exception means *drop this*. What follows is that difference.

**Its failures are not the API's.** A traceback here must not take the Flask
process down beside it, and a machine with no dev queue provisioned should say so
once and stop rather than crash-looping — `dev-up.sh` starts both, and a
developer who has not run `dev-aws-setup.sh` since this landed is the ordinary
case rather than an error.
"""

from studio_core.handlers.local.consumer import poll
from studio_core.services import callbacks


def main() -> int:
    return poll.serve(
        "callbacks",
        "STUDIO_CALLBACK_QUEUE_URL",
        "Nothing will close a run when its generation finishes. Provision this "
        "machine's dev stack with ./studio/scripts/dev-aws-setup.sh, or close "
        "runs by hand with `studio runs reconcile <run>`.",
        # A batch is rare — a developer submits runs one at a time — so this is
        # about not leaving a second completion waiting for a poll cycle behind
        # a slow video download.
        batch=10,
        handle=callbacks.handle,
        droppable=callbacks.Rejected,
    )


if __name__ == "__main__":
    raise SystemExit(main())
