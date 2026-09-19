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


#: An account picture's edge. Drawn at 24–80 CSS pixels and nowhere else, so
#: 512 is generous; the same number humbugg settles on.
AVATAR_SIZE = 512
AVATAR_QUALITY = 82
AVATAR_FORMATS = ("JPEG", "PNG", "WEBP")


def avatar(body: bytes) -> bytes:
    """One picture -> a square JPEG of `AVATAR_SIZE`, centre-cropped, metadata gone.

    Re-encoding is the point rather than a nicety. The bytes came from a
    browser as a data URL, so nothing about them is trusted: the format is
    checked against the three a browser would produce, the pixels are
    decoded once and written fresh, and an EXIF block — which is where a
    phone writes a location — never makes it to the bucket. A portrait and a
    landscape both work, because the crop takes the largest centred square.
    """
    from PIL import ImageOps

    im = _open(body)
    if im.format not in AVATAR_FORMATS:
        raise ValidationError("upload a PNG, JPEG or WebP image")
    # `exif_transpose` first: a phone photo is stored sideways with a tag
    # saying which way is up, and the tag is about to be thrown away.
    im = ImageOps.exif_transpose(im)
    square = ImageOps.fit(im, (AVATAR_SIZE, AVATAR_SIZE), centering=(0.5, 0.5))
    return _save(square, ".jpg", AVATAR_QUALITY)


#: What a still's poster is scaled to across — the same number `ffmpeg.poster`
#: uses for a clip, so one tile draws both at one size. A poster is drawn at a
#: few hundred CSS pixels wide and nowhere else; the original is what the
#: viewer opens.
POSTER_WIDTH = 640


def poster(src: str, dest_stem: str, width: int = POSTER_WIDTH) -> str:
    """A still scaled down for a tile, written beside `dest_stem`. -> the path.

    The image counterpart of `ffmpeg.poster`, and the one that carries the
    weight: a run's output is a 0.4 MB JPEG and an uploaded reference is a
    2–8 MB PNG or a phone photo, and every tile that drew one drew the whole
    file. A 640-wide JPEG at quality 80 is 30–80 KB.

    **Never upscaled.** A source already narrower than `width` is re-encoded
    as it is; a tile gains nothing from invented pixels.

    **The orientation is baked in.** A phone JPEG carries its rotation as an
    EXIF tag the browser honours and a resize would drop — so the picture is
    transposed first, and the poster stands the way the original displays.

    **A picture with transparency is written as WebP, and everything else as
    JPEG.** The library holds cut-outs with alpha that the browser draws over a
    checkerboard; a JPEG poster would fill the hole with black. The extension
    is decided here, off the decoded image, which is why this takes a stem
    rather than a path.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    # Decoded before anything is measured: `Image.open` reads only a header,
    # and a truncated or oversized file fails on `load` — an `OSError` or a
    # `DecompressionBombError` — which has to land here as a `ValidationError`,
    # the permanent kind, or a bad file would be redriven to the dead-letter
    # queue over bytes no retry can fix.
    try:
        with Image.open(src) as opened:
            opened.load()
            im = ImageOps.exif_transpose(opened) or opened.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(f"that object is not an image Pillow can read: {exc}") from None
    with im:
        alpha = im.mode in ("RGBA", "LA") or (
            im.mode == "P" and "transparency" in im.info)
        if im.width > width:
            height = max(1, round(im.height * width / im.width))
            im = im.resize((width, height), Image.Resampling.LANCZOS)
        if alpha:
            dest = dest_stem + ".webp"
            im.convert("RGBA").save(dest, "WEBP", quality=80, method=4)
        else:
            dest = dest_stem + ".jpg"
            im.convert("RGB").save(dest, "JPEG", quality=80, optimize=True,
                                   progressive=True)
    return dest
