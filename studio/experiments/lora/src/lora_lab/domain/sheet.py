"""Contact sheets — the artifact the human gates actually look at."""

import math
import pathlib

from PIL import Image, ImageDraw

TILE = 384


def contact_sheet(images: list[pathlib.Path], out: pathlib.Path, *, label: bool = True) -> None:
    if not images:
        raise ValueError("no images for the contact sheet")
    cols = math.ceil(math.sqrt(len(images)))
    rows = math.ceil(len(images) / cols)
    sheet = Image.new("RGB", (cols * TILE, rows * TILE), "black")
    draw = ImageDraw.Draw(sheet)
    for i, path in enumerate(sorted(images)):
        img = Image.open(path).convert("RGB")
        img.thumbnail((TILE, TILE))
        x, y = (i % cols) * TILE, (i // cols) * TILE
        sheet.paste(img, (x + (TILE - img.width) // 2, y + (TILE - img.height) // 2))
        if label:
            draw.text((x + 6, y + 6), path.stem, fill="white")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
