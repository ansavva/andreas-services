"""Build a labeled contact sheet (grid of thumbnails) for a character's images.

Every tile is captioned with the image's basename (e.g. ``<name>_3``) so a set of
reference / original images can be eyeballed at a glance — which pose, which
wardrobe — without opening each file. Re-run it whenever the
image set changes to refresh the sheet.

Two sources:

  # pull a character pool from the media store (characters/<name>/<pool>/)
  studio contact_sheet --character <name> --folder originals --out /tmp/<name>_originals.png

  # or build from a local directory of images already on disk
  studio contact_sheet --src /path/to/images --out /tmp/sheet.png

Write the sheet to a scratch/temp path — contact sheets of character images are
not kept in source control.

Images are laid out in natural-sorted order (<name>_1, <name>_2, … <name>_10) so tile
position is stable across runs. --cols / --cell tune the grid.
"""
import os
import pathlib
import sys
import tempfile

import click
from PIL import Image, ImageDraw, ImageFont

from studio_pipeline.adapters import store
from studio_pipeline.domain import characters as CHARACTER

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}


def _pool_images(root: str) -> list[dict]:
    """Every image under a pool, as `{"rel": …, "node": …}`, natural-sorted.

    The relative path is what the caption is built from; the node id is what the
    download goes through. Both, because the tree still has a shape a person
    reads (`face/front.webp`) and a node still has the identity a record holds.

    **Recursive, and it has to be** — the same call `characters.refs.ref_files`
    makes and for the same reason. `reference` is this command's DEFAULT pool
    and holds purpose subfolders rather than images, so a one-level listing
    reports the commonest invocation as an empty pool. `list_keys` was
    recursive by default and hid the decision; walking is now explicit.

    **A missing pool cannot arise here any more, and that is why this listing
    is unforgiving.** It used to go through `children_or_empty`, which swallowed
    a 404 so that a character with no `seed/` read as empty rather than raising
    — and it swallowed only a 404, because a refused pool must not read as a
    character with no images. `pool_folder` resolves the pool off the character
    record and creates it if somebody deleted it, so by the time this runs the
    folder exists. Anything raising from here is a real failure and is left to
    surface.
    """
    found: list[dict] = []

    def walk(node_id: str, prefix: str) -> None:
        for entry in store.children_of(node_id):
            rel = f"{prefix}{entry['name']}"
            if entry.get("kind") == "folder":
                walk(entry["id"], f"{rel}/")
            elif os.path.splitext(entry["name"])[1].lower() in IMG_EXTS:
                found.append({"rel": rel, "node": entry["id"]})

    walk(root, "")
    return sorted(found, key=lambda e: store.natural_key(e["rel"]))


def _gather_from_store(character: str, folder: str, dest: str,
                       group: str | None = None) -> list[str]:
    """Download a character pool into `dest`, one local file per image.

    **The local name carries the group** (`face_<name>_1.webp`), because it
    becomes the tile's caption and a basename does not survive the walk:
    `face/<name>_1` and `body/<name>_1` both exist, so bare basenames collided
    in one directory — the second download overwrote the first and the sheet
    showed one image twice under one label.
    """
    record = CHARACTER.resolve(character)
    root = CHARACTER.pool_folder(record, folder)
    # A pool is a tree, so sheeting one branch of it has to be expressible.
    # Without this the only way to eyeball `seed/current/` was to download the
    # folder by hand and come back through `--src`, which is the workaround
    # this command exists to remove.
    if group:
        root = store.ensure_child_folder(root["id"], group)
    where = f"{folder}/{group}" if group else folder
    images = _pool_images(root["id"])
    if not images:
        sys.exit(f"no images under {character}/{where}")
    os.makedirs(dest, exist_ok=True)
    paths = []
    for image in images:
        local = os.path.join(dest, image["rel"].replace("/", "_"))
        store.download_node(image["node"], pathlib.Path(local))
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
        # `store.natural_key` is the one definition of this sort in the package —
        # a second copy of the order that decides which image a model is handed is
        # exactly the drift worth not having.
        paths = sorted(paths, key=lambda p: store.natural_key(os.path.basename(p)))
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
@click.option("--group", default=None, help="A subfolder of the pool (e.g. seed/current).")
@click.option("--out", required=True, help="Output PNG path.")
@click.option("--src", help="Local directory of images (instead of --character).")
def contact_sheet(cell, character, cols, folder, group, out, src):
    if bool(character) == bool(src):
        raise click.UsageError("provide exactly one of --character or --src")

    if src:
        paths = _gather_from_dir(src)
    else:
        tmp = tempfile.mkdtemp(prefix=f"{character}-{folder}-")
        paths = _gather_from_store(character, folder, tmp, group)
    build(paths, out, cols, cell)
