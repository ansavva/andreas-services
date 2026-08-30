"""Local consumer for this machine's render queue. **Dev has no worker Lambda.**

`infra/envs/dev` declares the queue and declines the function, exactly as it does
for callbacks and for the same reason: a per-machine image build would cost
minutes per apply, and the render image is the larger of the two. So a stitch
submitted against a local API is done here, by the working tree, on the
developer's own ffmpeg — which is `imageio-ffmpeg`'s bundled binary either way,
so it is the same encoder prod runs.

`dev-up.sh` starts this beside `callback_consumer`. The loop is
`consumer/poll.py`; what is here is which queue and which failures to drop.
"""

from studio_core.handlers.local.consumer import poll
from studio_core.services import render


def main() -> int:
    return poll.serve(
        "render",
        "STUDIO_RENDER_QUEUE_URL",
        "Nothing will stitch a scene or pull a frame. Provision this machine's "
        "dev stack with ./studio/scripts/dev-aws-setup.sh.",
        # ONE AT A TIME, matching prod's event source mapping. A stitch is
        # minutes; taking ten would serialise nine jobs behind the first under
        # one visibility timeout, and on a laptop it would also mean ten clips
        # on disk at once.
        batch=1,
        handle=render.handle,
        droppable=render.RenderError,
    )


if __name__ == "__main__":
    raise SystemExit(main())
