"""Ask the service to render something, and wait for it.

Neither ffmpeg nor Pillow ships in this wheel: stitching a scene, cutting a
movie, pulling a frame, sampling a contact grid and laying out a contact sheet
are all done by a worker Lambda with ffmpeg in its image, and this is how a
terminal asks for one.

    studio scenes assemble …
        │
        ├─ resolve the parts here — `latest`, `#N`, "that scene is not cut yet"
        ├─ POST /api/renders            -> a `render-<uuid>` row, `queued`
        ├─ poll GET /api/renders/<id>   -> `running`, then `succeeded`/`failed`
        └─ download the node it produced, if a local path was asked for

## Why resolution stays on this side

A runref is `<project>/latest#2`; a sceneref is `<project>/<slug>`; "this run
produced two videos, say which" and "that scene is planned but not assembled"
are refusals a person acts on. All of them belong in front of the person, not at
the far end of a queue where they arrive twenty seconds later as a failed row.
So the CLI resolves every input to a **node id** and the job carries node ids.

## What waiting means

The same sentence as `engine/submit.wait_for`:
**`Ctrl-C` abandons a wait, not the work.** The render is being done by something
else; interrupting this leaves the job running and the row is still there to
read. A timeout is likewise not a failure — it is this terminal's patience
running out, and the message says how to pick the thread back up.

## What a job produces

One node, in a folder the caller named, plus a report. `fetch` is what brings it
back to disk for the commands that print a local path. The bytes go
worker → S3 → here: one download per command rather than one per input.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.errors import die

#: How often to ask. A stitch is tens of seconds at best, so a tighter loop is
#: requests for nothing; a looser one is dead air at the end of a fast job.
POLL_SECONDS = 2

#: How long to wait before giving up on the *wait*. Comfortably past the
#: worker's own 10-minute timeout, so this terminal is never the first thing to
#: give up on a job that is still going — a job that will fail has already
#: failed by then, and the row says so.
TIMEOUT_SECONDS = 900

TERMINAL = frozenset({"succeeded", "failed"})


class RenderError(RuntimeError):
    """A render was refused, failed, or was waited on for too long."""


def submit(kind: str, params: dict, *, what: str,
           timeout: int = TIMEOUT_SECONDS) -> dict:
    """Enqueue one job and wait for it. -> the job's `result`.

    `what` is the sentence fragment that names this job in a message — "the
    cut", "the frame" — so a failure reads as a thing a person recognises rather
    than as a job id.
    """
    try:
        job = entities.create_render(kind, params)
    except api.ApiError as exc:
        raise RenderError(f"could not ask for {what}: {exc}") from exc
    return wait_for(job["id"], what=what, timeout=timeout)


def wait_for(render_id: str, *, what: str, timeout: int = TIMEOUT_SECONDS) -> dict:
    """Watch a job row until it settles. -> its `result`.

    Statuses are printed to **stderr** as they change, so the progress a person
    watches does not end up in the JSON a caller pipes.
    """
    deadline = time.time() + timeout
    seen = None
    while True:
        try:
            job = entities.get_render(render_id)
        except api.ApiError as exc:
            raise RenderError(
                f"could not read render {render_id} while waiting: {exc}\n"
                f"       The work is unaffected; it is being done elsewhere."
            ) from exc

        status = job.get("status")
        if status != seen:
            print(f"  {what}: {status}", file=sys.stderr)
            seen = status
        if status == "succeeded":
            return job.get("result") or {}
        if status == "failed":
            raise RenderError(f"{what} failed: {job.get('error') or 'no reason recorded'}")
        if time.time() > deadline:
            raise RenderError(
                f"gave up waiting for {what} after {timeout}s; render {render_id} "
                f"is {status} and is still going.\n"
                f"       Nothing was lost — it finishes on its own, and the row "
                f"records what it did.")
        time.sleep(POLL_SECONDS)


def part(node: str, **extra) -> dict:
    """One input to a job. A node id, plus whatever the job records beside it.

    A helper rather than a literal at every call site because `parts` is the one
    field every kind shares and the ORDER of it is the meaning — a cut order, a
    tile order — so it is worth having one name for.
    """
    return {"node": node, **{k: v for k, v in extra.items() if v is not None}}


def fetch(asset: dict, dest_dir: str, name: str | None = None) -> str:
    """Bring a produced node down to disk. -> the local path.

    For the commands that print a path a person then opens. The file exists in
    the library either way — that is not optional any more, because the bytes are
    made in a worker and S3 is how they get here — so this is a copy and never a
    move.
    """
    os.makedirs(dest_dir, exist_ok=True)
    local = os.path.join(dest_dir, name or asset.get("name") or asset["node"])
    store.download_node(asset["node"], pathlib.Path(local))
    return local


def scratch(record: dict, *names: str) -> str:
    """A folder under an entity's root, made if it is absent. -> the node id.

    **Every render writes into the library**, including the ones that used to
    write only to a temp directory: a worker has no other way to hand bytes back.
    So `frames grid` and `contact-sheet` need somewhere to land, and it is a
    `renders/` (or `review/`) folder resolved by name and created on demand —
    convention, exactly like `chains/`, and deletable by anyone who wants the
    space back.

    These commands accumulate output, visibly, in a folder named for what it
    holds.
    """
    return store.folder_path(record, *names)["id"]


def one_video(nodes: list[str], ref: str) -> str:
    """Exactly one video node, or a refusal naming the ambiguity.

    Kept on this side of the wire deliberately: "this run has three clips, say
    which" is a sentence with an action in it, and a person should read it before
    a job is queued rather than after one fails.
    """
    if not nodes:
        die(f"{ref}: no video to work from")
    if len(nodes) > 1:
        die(f"{ref}: {len(nodes)} videos — append #N to pick one")
    return nodes[0]
