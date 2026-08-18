"""Build a labeled contact sheet (grid of thumbnails) for a character's images.

Every tile is captioned with the image's basename (e.g. ``<name>_3``) so a set of
reference / original images can be eyeballed at a glance — which pose, which
wardrobe — without opening each file. Re-run it whenever the
image set changes to refresh the sheet.

Two sources:

  # pull a character pool straight from S3 (characters/<name>/<pool>/)
  studio contact_sheet --character <name> --folder originals --out /tmp/<name>_originals.png

  # or build from a local directory of images already on disk
  studio contact_sheet --src /path/to/images --out /tmp/sheet.png

Write the sheet to a scratch/temp path — contact sheets of character images are
not kept in source control.

Images are laid out in natural-sorted order (<name>_1, <name>_2, … <name>_10) so tile
position is stable across runs. --cols / --cell tune the grid.
"""
import os
import sys
import tempfile

import click
from PIL import Image, ImageDraw, ImageFont

from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.domain import paths as P

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}


def _natural_key(name: str):
    import re

    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _gather_from_s3(character: str, folder: str, dest: str) -> list[str]:
    s3 = s3c.client()
    prefix = P.char_pool_prefix(character, folder)
    keys = s3c.list_keys(s3, prefix)
    if not keys:
        sys.exit(f"no objects under {s3c.key(prefix)}/")
    os.makedirs(dest, exist_ok=True)
    paths = []
    for k in keys:
        base = os.path.basename(k)
        if os.path.splitext(base)[1].lower() not in IMG_EXTS:
            continue
        local = os.path.join(dest, base)
        s3.download_file(s3c.BUCKET, k, local)
        paths.append(local)
    return paths


def _gather_from_dir(src: str) -> list[str]:
    return [
        os.path.join(src, f)
        for f in os.listdir(src)
        if os.path.splitext(f)[1].lower() in IMG_EXTS
    ]


def _load_font(size: int):
    for p in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def build(paths: list[str], out: str, cols: int, cell: int,
          captions: list[str] | None = None, quiet: bool = False) -> str:
    """Lay images out in a labelled grid.

    `captions` serves the other caller: a payload review, where the order IS the
    meaning — tile N is the image a prompt cites as `[ImageN]` — and the caption
    has to say that rather than repeat a filename. Given captions, the order is
    taken as authoritative and left alone; without them the sheet is
    natural-sorted and captioned by basename, which is what browsing a pool wants.
    """
    if captions is None:
        paths = sorted(paths, key=lambda p: _natural_key(os.path.basename(p)))
        captions = [os.path.splitext(os.path.basename(p))[0] for p in paths]
    if not paths:
        sys.exit("no images to lay out")
    label_h = max(20, cell // 12)
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    font = _load_font(max(14, label_h - 6))
    for idx, path in enumerate(paths):
        r, c = divmod(idx, cols)
        x, y = c * cell, r * (cell + label_h)
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((cell, cell))
            sheet.paste(im, (x + (cell - im.width) // 2, y + label_h + (cell - im.height) // 2))
        except Exception as e:
            draw.text((x + 6, y + label_h + 6), f"[{e}]", fill="red", font=font)
        draw.rectangle([x, y, x + cell, y + label_h], fill="black")
        draw.text((x + 6, y + 3), captions[idx], fill="white", font=font)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    if not quiet:
        print(f"{out}  ({sheet.width}x{sheet.height}, {len(paths)} tiles)")
    return out


@click.command(help=__doc__)
@click.option("--cell", type=int, default=300, help="Thumbnail cell size in px (default: 300).")
@click.option("--character", help="Character name; pull characters/<name>/<pool>/ from S3.")
@click.option("--cols", type=int, default=5, help="Grid columns (default: 5).")
@click.option("--folder", type=click.Choice(["archive", "corpus", "reference", "seed"]), default='reference', help="Which character pool to sheet (default: reference).")
@click.option("--out", required=True, help="Output PNG path.")
@click.option("--src", help="Local directory of images (instead of --character).")
def contact_sheet(cell, character, cols, folder, out, src):
    if bool(character) == bool(src):
        raise click.UsageError("provide exactly one of --character or --src")

    if src:
        paths = _gather_from_dir(src)
    else:
        tmp = tempfile.mkdtemp(prefix=f"{character}-{folder}-")
        paths = _gather_from_s3(character, folder, tmp)
    build(paths, out, cols, cell)
