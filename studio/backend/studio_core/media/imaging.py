"""Pillow operations on one image: re-encode, and cut a rectangle out.

Ported from `objects/convert.py` and `objects/crop.py`, minus everything those
files did around the edges — resolving a runref, numbering a pool entry,
printing. What is left is the actual work, and it is small: open bytes, do one
thing, save bytes.

**These are the two operations that do NOT go on the render queue**, and the
issue that moved this code asked the question directly. Both are sub-second on a
single image, so a queue round trip — enqueue, poll, poll again — costs more
wall clock than the work and buys nothing: there is no output large enough to
exceed a Lambda response, no encode long enough to threaten the 30-second API
Gateway ceiling, and nothing to stream. So `routes/images.py` answers them
synchronously in the API image, and the API image carries Pillow and not ffmpeg.

Pillow is ~3 MB installed. ffmpeg through `imageio-ffmpeg` is ~80 MB, and every
folder listing would have paid for it.
"""

from __future__ import annotations

import io

from studio_core.errors import ValidationError

#: `--to png` -> `.png`. Kept spelled as the CLI spells it, because the CLI's
#: option list is frozen in `tests/contracts/cli_surface_reference.json`.
EXT_FOR = {"png": ".png", "jpg": ".jpg", "jpeg": ".jpg", "webp": ".webp"}
PIL_FORMAT = {".png": "PNG", ".jpg": "JPEG", ".webp": "WEBP"}
CONTENT_TYPE = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def parse_box(text: str) -> tuple[int, int, int, int]:
    """`left,top,right,bottom` -> a 4-tuple of ints.

    Its own function because the error messages are the point: a box is four
    numbers typed by a person or pasted from a detector, and every way of
    getting it wrong should say which way. They are `ValidationError` here
    rather than a process exit, so the 400 carries the same sentence the CLI
    used to print.
    """
    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) != 4:
        raise ValidationError(
            f"box takes four numbers, LEFT,TOP,RIGHT,BOTTOM — got {len(parts)}: {text!r}")
    try:
        left, top, right, bottom = (int(float(p)) for p in parts)
    except ValueError:
        raise ValidationError(
            f"box must be four numbers, LEFT,TOP,RIGHT,BOTTOM — got {text!r}") from None
    if right <= left or bottom <= top:
        raise ValidationError(
            f"box is empty or inverted: {left},{top},{right},{bottom} "
            "(it is LEFT,TOP,RIGHT,BOTTOM, not LEFT,TOP,WIDTH,HEIGHT)")
    return left, top, right, bottom


def clamp(box: tuple[int, int, int, int], width: int, height: int
          ) -> tuple[int, int, int, int]:
    """Pull a box inside the image. Refuses one that misses it entirely.

    Clamped rather than refused because a box a few pixels past an edge is what
    padding a detection produces, and failing on it would make every caller do
    the clamping. A box with no overlap at all IS refused — that is a mistake,
    not a rounding.
    """
    left, top, right, bottom = box
    inside = (max(0, min(left, width)), max(0, min(top, height)),
              max(0, min(right, width)), max(0, min(bottom, height)))
    if inside[2] <= inside[0] or inside[3] <= inside[1]:
        raise ValidationError(
            f"box {left},{top},{right},{bottom} is entirely outside the "
            f"{width}x{height} image.")
    return inside


def _open(body: bytes):
    from PIL import Image, UnidentifiedImageError

    try:
        return Image.open(io.BytesIO(body))
    except UnidentifiedImageError:
        raise ValidationError("that object is not an image Pillow can read") from None


def _save(im, target_ext: str, quality: int) -> bytes:
    if target_ext == ".jpg" and im.mode in ("RGBA", "P", "LA"):
        im = im.convert("RGB")  # JPEG has no alpha channel
    buf = io.BytesIO()
    im.save(buf, PIL_FORMAT[target_ext],
            **({"quality": quality} if target_ext in (".jpg", ".webp") else {}))
    return buf.getvalue()


def convert(body: bytes, target_ext: str, *, quality: int = 95) -> bytes:
    """Re-encode one image. The source is never modified — this returns new bytes."""
    if target_ext not in PIL_FORMAT:
        raise ValidationError(f"cannot write {target_ext}")
    return _save(_open(body), target_ext, quality)


def crop(body: bytes, box: tuple[int, int, int, int], target_ext: str,
         *, quality: int = 95) -> tuple[bytes, dict]:
    """Cut a rectangle out. -> (bytes, a report of what was actually cut).

    The report is returned rather than printed for the reason `ffmpeg.stitch`
    returns one: the clamp is a thing that silently happened to somebody's box,
    and the caller is what decides whether to say so.
    """
    if target_ext not in PIL_FORMAT:
        raise ValidationError(f"cannot write {target_ext}")
    im = _open(body)
    inside = clamp(box, im.width, im.height)
    cut = im.crop(inside)
    return _save(cut, target_ext, quality), {
        "source": {"width": im.width, "height": im.height},
        "requested": list(box),
        "box": list(inside),
        "clamped": inside != tuple(box),
        "width": cut.width,
        "height": cut.height,
    }
