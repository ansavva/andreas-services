"""`studio crop` — cut a rectangle out of an image in the media tree.

**The operation the pipeline had no verb for.** Framing is not a generation and
not a re-encode, so it fell between every command here: a person cropping a
seed photo to its subject did it on their laptop, uploaded the result, and threw
away the only record of what was cut. Seventy-five images were framed that way
in one session and none of it was repeatable — the boxes lived in a scratch
directory and the library held a file whose provenance was "someone cropped it".

This does the same cut through `adapters/store`, so the box is stated, printed,
and the source is left alone.

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

import io
import os
import sys

import click

from studio_pipeline.adapters import api, store
from studio_pipeline.errors import die, reports
from studio_pipeline.objects.convert import (
    CONTENT_TYPE,
    EXT_FOR,
    PIL_FORMAT,
    _into_input_pool,
    _source_name,
)
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


def clamp(box: tuple[int, int, int, int], width: int, height: int
          ) -> tuple[int, int, int, int]:
    """Pull a box inside the image. Refuses one that misses it entirely."""
    left, top, right, bottom = box
    inside = (max(0, min(left, width)), max(0, min(top, height)),
              max(0, min(right, width)), max(0, min(bottom, height)))
    if inside[2] <= inside[0] or inside[3] <= inside[1]:
        die(f"--box {left},{top},{right},{bottom} is entirely outside the "
            f"{width}x{height} image.")
    return inside


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
@reports(api.NotFound, api.Forbidden, R.RunError)
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

    wanted = parse_box(box)
    source_ext = os.path.splitext(_source_name(key))[1].lower()
    target_ext = EXT_FOR[to] if to else (source_ext if source_ext in PIL_FORMAT else ".png")

    from PIL import Image

    try:
        body = store.read_node(key) if key.startswith("node-") else store.read(key)
    except api.NotFound:
        die(f"no such object: {key}")
    im = Image.open(io.BytesIO(body))
    inside = clamp(wanted, im.width, im.height)
    cut = im.crop(inside)
    if target_ext == ".jpg" and cut.mode in ("RGBA", "P", "LA"):
        cut = cut.convert("RGB")          # JPEG has no alpha channel
    buf = io.BytesIO()
    cut.save(buf, PIL_FORMAT[target_ext],
             **({"quality": quality} if target_ext in (".jpg", ".webp") else {}))
    data = buf.getvalue()

    if dest_key:
        dst = dest_key.strip("/")
        if "/" in dst:
            store.folder(dst.rsplit("/", 1)[0])
        store.write(dst, data, content_type=CONTENT_TYPE[target_ext])
    else:
        dst = _into_input_pool(add_input, data, target_ext)

    print(dst)
    note = "" if inside == wanted else f" (clamped from {','.join(str(v) for v in wanted)})"
    print(f"cropped {os.path.basename(_source_name(key))} "
          f"{im.width}x{im.height} -> {cut.width}x{cut.height} "
          f"at {','.join(str(v) for v in inside)}{note}; source untouched",
          file=sys.stderr)
    return 0
