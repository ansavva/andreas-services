"""A labelled contact sheet: a grid of thumbnails, each captioned.

Ported from `domain/contact_sheet.py`, which had two callers and kept both:

* **Browsing a pool.** Tiles are natural-sorted and captioned with each image's
  basename, so a set of reference images can be eyeballed at a glance — which
  pose, which wardrobe — without opening each file.
* **A payload review.** The order IS the meaning: tile N is the image a prompt
  cites as `[ImageN]`, and the caption has to say that rather than repeat a
  filename. Given captions, the order is taken as authoritative and left alone.

What did not move is the gathering. The CLI half walked a character's pool and
downloaded it; that is catalog work and lives in `services/render.py` now. This
takes local paths and captions and lays them out.

**A font is not guaranteed and the fallback is not equivalent.** The CLI looked
for Arial on macOS and DejaVu on Debian; a Lambda image has neither unless it is
installed, so the render image installs `dejavu-sans-fonts` and the search list
below names its path first. `ImageFont.load_default()` still backs it, and it is
a bitmap font that ignores the size argument — so a sheet that fell through to
it is legible but tiny. Worth knowing when a sheet comes back looking wrong.
"""

from __future__ import annotations

import os
import re

#: Where a TrueType font might be. First hit wins.
FONT_PATHS = (
    # What the render image installs. Named first so the common case is one stat.
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}

_NUM = re.compile(r"(\d+)")


def natural_key(name: str):
    """`<name>_2` before `<name>_10`. One definition, shared with the store.

    A second copy of the order that decides which image a model is handed is
    exactly the drift worth not having, so this mirrors `adapters/store.natural_key`
    on the CLI side and `services/browse` on this one.
    """
    return [int(part) if part.isdigit() else part.lower() for part in _NUM.split(name)]


def _load_font(size: int):
    from PIL import ImageFont

    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def build(paths: list[str], out: str, cols: int, cell: int,
          captions: list[str] | None = None) -> dict:
    """Lay images out in a labelled grid. -> a report of what was drawn.

    Returns rather than prints, for the reason every function in this package
    does: the caller is a worker, and a `print` in a worker goes to a log nobody
    correlates with the job that produced it.
    """
    from PIL import Image, ImageDraw

    if captions is None:
        paths = sorted(paths, key=lambda p: natural_key(os.path.basename(p)))
        captions = [os.path.splitext(os.path.basename(p))[0] for p in paths]
    if not paths:
        raise ValueError("no images to lay out")

    label_h = max(20, cell // 12)
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    font = _load_font(max(14, label_h - 6))
    broken = []
    for idx, path in enumerate(paths):
        r, c = divmod(idx, cols)
        x, y = c * cell, r * (cell + label_h)
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((cell, cell))
            sheet.paste(im, (x + (cell - im.width) // 2,
                             y + label_h + (cell - im.height) // 2))
        except Exception as exc:  # noqa: BLE001 — one unreadable tile must not lose the sheet
            draw.text((x + 6, y + label_h + 6), f"[{exc}]", fill="red", font=font)
            broken.append(captions[idx])
        draw.rectangle([x, y, x + cell, y + label_h], fill="black")
        draw.text((x + 6, y + 3), captions[idx], fill="white", font=font)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    return {"width": sheet.width, "height": sheet.height, "tiles": len(paths),
            "cols": cols, "cell": cell, "captions": captions,
            # Named rather than swallowed. The CLI drew `[error]` into the tile
            # and left it at that, which is fine on a screen somebody is looking
            # at and invisible on a record.
            "unreadable": broken}
