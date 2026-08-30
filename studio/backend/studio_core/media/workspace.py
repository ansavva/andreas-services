"""Where a render's temp files live, and what happens when `/tmp` fills.

**The third question the issue that moved this code asked**, and it is a real
one: the CLI stitched on a laptop with a disk measured in hundreds of gigabytes,
and a Lambda has `/tmp` and whatever `ephemeral_storage` was set to. A movie is
several scenes downloaded, plus the cut, so the peak is roughly *twice* the sum
of the inputs.

Three things, in the order they matter:

* **The job declares what it will need before it downloads anything.** Every
  input is a node with a recorded `size`, so the total is known from the catalog
  without moving a byte. `reserve` compares it against real free space and
  refuses up front — one clear sentence on the render row, rather than an
  `OSError: [Errno 28] No space left on device` from inside ffmpeg after eight
  minutes and several hundred megabytes of transfer.
* **The workspace is removed on the way out, success or failure.** `/tmp`
  survives a warm start, so a job that died mid-download would otherwise leave
  its half-file for the next invocation to inherit, and the disk fills one
  failure at a time. `services/generate.py` learned this the same way for the
  callback worker.
* **Space is checked, never assumed from the setting.** `ephemeral_storage` is
  what Terraform asked for; `shutil.disk_usage` is what the container has, and
  the second is the one that runs out.

`HEADROOM` is a flat reserve rather than a percentage. The output of a stream
copy is the sum of its inputs and the output of a re-encode is usually smaller,
so `2x + headroom` covers both; ffmpeg's own scratch is negligible beside the
files themselves.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile

logger = logging.getLogger(__name__)

#: Bytes left free after a job's own peak. Room for the concat list, a frame or
#: two, and whatever the runtime writes without asking.
HEADROOM = 256 * 1024 * 1024


class OutOfSpace(RuntimeError):
    """This job does not fit on this disk. **Not transient** — see `services/render`.

    A redrive re-downloads the same inputs into the same `/tmp` and fails
    identically, three times, and then fills the dead-letter queue with a
    message whose only remedy is a Terraform change. So it closes the job
    `failed` with a sentence naming both numbers, which is the thing that tells
    somebody which number to change.
    """


class Workspace:
    """A scratch directory for one job, removed when the job ends.

    A context manager rather than a `mkdtemp` call, because the removal is the
    part that matters and a `finally` in every job body is a `finally` one job
    body will forget.
    """

    def __init__(self, prefix: str = "render-", root: str | None = None):
        self.root = root or tempfile.gettempdir()
        self.prefix = prefix
        self.path: str = ""

    def __enter__(self) -> "Workspace":
        os.makedirs(self.root, exist_ok=True)
        self.path = tempfile.mkdtemp(prefix=self.prefix, dir=self.root)
        return self

    def __exit__(self, *_exc) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
        self.path = ""

    def at(self, *names: str) -> str:
        """A path inside the workspace, with its parent made."""
        full = os.path.join(self.path, *names)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return full

    def free(self) -> int:
        return shutil.disk_usage(self.path or self.root).free

    def reserve(self, input_bytes: int, *, factor: int = 2) -> None:
        """Refuse the job now if its declared peak will not fit.

        `factor` is 2 for anything that writes an output the size of its inputs
        — a stitch — and 1 for a job whose output is a still: a contact sheet of
        a 200 MB clip is a JPEG.
        """
        want = input_bytes * factor + HEADROOM
        free = self.free()
        if want > free:
            raise OutOfSpace(
                f"this render needs about {want // 1048576} MB of scratch space and "
                f"{free // 1048576} MB is free. Raise `worker_ephemeral_storage` in "
                "`studio/infra/modules/render`, or cut fewer inputs at once."
            )
        logger.info("workspace %s: %d MB free, reserving ~%d MB",
                    self.path, free // 1048576, want // 1048576)
