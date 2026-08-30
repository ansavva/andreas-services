"""`studio crop` — cut a rectangle out of an image in the media tree.

**The operation the pipeline had no verb for.** Framing is not a generation and
not a re-encode, so it fell between every command here: a person cropping a
seed photo to its subject did it on their laptop, uploaded the result, and threw
away the only record of what was cut. Seventy-five images were framed that way
in one session and none of it was repeatable — the boxes lived in a scratch
directory and the library held a file whose provenance was "someone cropped it".

This does the same cut through the **API**, so the box is stated, printed,
recorded, and the source is left alone.

**Pillow used to be in this wheel and is in the API image now.** A crop is one
`POST /api/images/crop`: sub-second on a single image, so it is answered
synchronously rather than going on the render queue that stitching uses — an
enqueue plus two polls would cost more wall clock than the work, and Pillow is
3 MB where ffmpeg is 80. `backend/studio_core/routes/images.py` states the split.

  # explicit box, into the project's input pool
  studio crop --key <node> --box 120,40,880,1400 --add-input <project>

  # a run's output, to a named destination
  studio crop --run <project>/latest#1 --box 0,0,1179,2196 \
      --dest-key characters/<name>/seed/current/<file>.jpg

**The box is LEFT,TOP,RIGHT,BOTTOM in source pixels**, the same order and
meaning Pillow's `crop` takes and the same a detector reports. It is clamped to
the image rather than refused: a box a few pixels past an edge is what padding a
detection produces, and failing on it would make every caller do the clamping.
A box with no overlap at all IS refused — that is a mistake, not a rounding.

**What this deliberately does not do is find the subject.** Face and body
detection are platform work — the session that prompted this used macOS Vision —
and a wrong box is worse than no command. Detect wherever you like; state the
box here.

Format follows the source unless `--to` says otherwise. The source is never
modified: a run's output is append-only history, so it is copied, not cut in
place.
"""
from __future__ import annotations

import os
import sys

import click

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.errors import die, reports
from studio_pipeline.objects.convert import _source_name, destination
from studio_pipeline.domain import runs as R


def parse_box(text: str) -> tuple[int, int, int, int]:
    """`left,top,right,bottom` -> a 4-tuple of ints.

    Its own function because the error messages are the point: a box is four
    numbers typed by a person or pasted from a detector, and every way of
    getting it wrong should say which way.
    """
    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) != 4:
        die(f"--box takes four numbers, LEFT,TOP,RIGHT,BOTTOM — got {len(parts)}: {text!r}")
    try:
        left, top, right, bottom = (int(float(p)) for p in parts)
    except ValueError:
        die(f"--box must be four numbers, LEFT,TOP,RIGHT,BOTTOM — got {text!r}")
    if right <= left or bottom <= top:
        die(f"--box is empty or inverted: {left},{top},{right},{bottom} "
            "(it is LEFT,TOP,RIGHT,BOTTOM, not LEFT,TOP,WIDTH,HEIGHT)")
    return left, top, right, bottom


@click.command(help=__doc__)
@click.option("--add-input", help="Write into PROJECT's input pool as <project>_in_<n>.")
@click.option("--box", required=True, help="LEFT,TOP,RIGHT,BOTTOM in source pixels.")
@click.option("--dest-key", help="Explicit destination name path instead.")
@click.option("--key", help="Source node id or name path.")
@click.option("--project", help="Default project for a bare runref.")
@click.option("--quality", type=int, default=95, help="JPEG/WebP quality (default 95).")
@click.option("--run", help="Source runref, e.g. <name>/latest#1.")
@click.option("--to", type=click.Choice(["jpeg", "jpg", "png", "webp"]),
              help="Output format (default: the source's).")
# `api.ApiError` joins the list because the box is decided by the route now:
# a box entirely outside the image is a 400, and without this the refusal
# reaches a person as a traceback instead of the sentence it names.
@reports(api.NotFound, api.Forbidden, api.ApiError, R.RunError)
def crop(add_input, box, dest_key, key, project, quality, run, to):
    if not add_input and not dest_key:
        die("choose a destination: --add-input PROJECT (usual) or --dest-key KEY.")
    if bool(run) == bool(key):
        die("name exactly one source: --key or --run.")

    if run:
        nodes = R.resolve_output_nodes(run, project, kinds=R.IMG_EXTS)
        if len(nodes) > 1:
            die(f"runref matched {len(nodes)} images; add #N to pick one: {nodes}")
        key = nodes[0]

    # **The box is parsed on both sides, and that is not duplication worth
    # removing.** Four numbers typed by a person is the commonest thing to get
    # wrong here, and a refusal that arrives before a request beats one that
    # arrives as a 400 — while the route has to check anyway, because the SPA
    # and anything else that posts are not this command.
    wanted = parse_box(box)

    node = key if key.startswith("node-") else store.resolve(key)["id"]
    folder, name = destination(add_input, dest_key)
    reply = entities.crop_image(node, ",".join(str(v) for v in wanted),
                                to=to, dest=folder, name=name, quality=quality)

    print(reply["image"]["node"])
    # **The clamp is reported because a silent one is a box that is not the box
    # anybody stated.** The route decides it — it is the only side that has read
    # the image's dimensions — and says so in the reply.
    note = "" if not reply["clamped"] else \
        f" (clamped from {','.join(str(v) for v in reply['requested'])})"
    print(f"cropped {os.path.basename(_source_name(key))} "
          f"{reply['source']['width']}x{reply['source']['height']} -> "
          f"{reply['width']}x{reply['height']} "
          f"at {','.join(str(v) for v in reply['box'])}{note}; source untouched",
          file=sys.stderr)
    return 0
