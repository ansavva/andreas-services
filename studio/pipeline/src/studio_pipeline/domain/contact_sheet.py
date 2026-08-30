"""Build a labeled contact sheet (grid of thumbnails) for a character's images.

Every tile is captioned with the image's basename (e.g. ``<name>_3``) so a set of
reference / original images can be eyeballed at a glance — which pose, which
wardrobe — without opening each file. Re-run it whenever the image set changes to
refresh the sheet.

  # pull a character pool from the media store
  studio contact_sheet --character <name> --folder originals --out /tmp/sheet.png

Images are laid out in natural-sorted order (<name>_1, <name>_2, … <name>_10) so
tile position is stable across runs. --cols / --cell tune the grid.

THE LAYOUT IS DONE BY THE SERVICE
---------------------------------
**Pillow used to be in this wheel.** It is in the render worker's image now, so
this resolves a pool to node ids, enqueues a `sheet` render job and waits — the
images are never downloaded here, and neither is the font.

It is on the **queue** rather than being a synchronous route like `convert` and
`crop`, and the difference is what is bounded. A conversion is one image and is
over before a poll would return. A sheet is N downloads where N is a character
pool — fifty-four stills in the published dev fixture — so it is minutes of
transfer in the worst case and belongs where there is a disk and a budget.

The sheet lands in the character's `review/` folder, resolved by name and created
if absent. That is a change: it used to exist only at `--out`. A worker has no way
to hand bytes back except through S3, and a sheet only anybody's terminal can see
is half of what a sheet is for. `--out` still writes the local copy.

**`--src` is refused.** It took a directory of images already on disk, which
cannot be laid out by a worker that has never seen them. Upload them first — they
belong in the library if they are worth sheeting — and address the pool.
"""
import os
import sys

import click

from studio_pipeline.adapters import api, store
from studio_pipeline.errors import reports
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import renders as RENDER

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}

#: Where a character's sheets land. Convention, resolved by name under the
#: character's root and created if absent — the same self-healing rule
#: `scenes`' `review/` and `projects`' `chains/` follow.
REVIEW_FOLDER = "review"


def pool_images(root: str) -> list[dict]:
    """Every image under a pool, as `{"rel": …, "node": …}`, natural-sorted.

    The relative path is what the caption is built from; the node id is what the
    sheet is built from. Both, because the tree still has a shape a person reads
    (`face/front.webp`) and a node still has the identity a record holds.

    **Recursive, and it has to be** — the same call `characters.refs.ref_files`
    makes and for the same reason. `reference` is this command's DEFAULT pool and
    holds purpose subfolders rather than images, so a one-level listing reports
    the commonest invocation as an empty pool.

    **A missing pool cannot arise here any more**, which is why this listing is
    unforgiving: `pool_folder` resolves the pool off the character record and
    creates it if somebody deleted it, so by the time this runs the folder
    exists. Anything raising from here is a real failure and is left to surface.
    """
    found: list[dict] = []

    def walk(node_id: str, prefix: str) -> None:
        for entry in store.children_of(node_id):
            rel = f"{prefix}{entry['name']}"
            if entry.get("kind") == "folder":
                walk(entry["id"], f"{rel}/")
            elif "." + rel.rsplit(".", 1)[-1].lower() in IMG_EXTS:
                found.append({"rel": rel, "node": entry["id"]})

    walk(root, "")
    return sorted(found, key=lambda e: store.natural_key(e["rel"]))


@click.command(help=__doc__)
@click.option("--cell", type=int, default=300, help="Thumbnail cell size in px (default: 300).")
@click.option("--character", help="Character name; pull characters/<name>/<pool>/ from S3.")
@click.option("--cols", type=int, default=5, help="Grid columns (default: 5).")
@click.option("--folder", type=click.Choice(["archive", "corpus", "reference", "seed"]), default='reference', help="Which character pool to sheet (default: reference).")
@click.option("--group", default=None, help="A subfolder of the pool (e.g. seed/current).")
@click.option("--out", required=True, help="Output PNG path.")
@click.option("--src", help="Local directory of images (instead of --character). No longer supported.")
@reports(api.ApiError, RENDER.RenderError)
def contact_sheet(cell, character, cols, folder, group, out, src):
    if src:
        # Refused rather than quietly ignored. The layout happens in a worker
        # that can only see the library, so there is no version of this that
        # works — and a wrong sheet is worse than a refusal that names the fix.
        sys.exit("--src is no longer supported: the sheet is laid out by the "
                 "service, which cannot see this machine's disk.\n"
                 "       Upload the images first (studio upload), then sheet the "
                 "pool they landed in.")
    if not character:
        raise click.UsageError("provide --character")

    record = CHARACTER.resolve(character)
    root = CHARACTER.pool_folder(record, folder)
    # A pool is a tree, so sheeting one branch of it has to be expressible.
    # Without this the only way to eyeball `seed/current/` was to download the
    # folder by hand, which is the workaround this command exists to remove.
    if group:
        root = store.ensure_child_folder(root["id"], group)
    where = f"{folder}/{group}" if group else folder
    images = pool_images(root["id"])
    if not images:
        sys.exit(f"no images under {character}/{where}")

    # **Captions carry the group**, because a basename does not survive the walk:
    # `face/<name>_1` and `body/<name>_1` both exist, so bare basenames collided
    # and the sheet showed one image twice under one label.
    result = RENDER.submit("sheet", {
        "parts": [RENDER.part(image["node"], caption=image["rel"].rsplit(".", 1)[0])
                  for image in images],
        "cols": cols, "cell": cell,
        "dest": store.ensure_child_folder(record["root"], REVIEW_FOLDER)["id"],
        "name": f"{character}-{folder}.png",
    }, what="the sheet")

    sheet = result["sheet"]
    print(sheet["node"])
    print(f"  ({result['width']}x{result['height']}, {result['tiles']} tiles)",
          file=sys.stderr)
    if result.get("unreadable"):
        # Named rather than drawn into a tile and forgotten. The worker draws the
        # error where the image should be, which is right for a person looking at
        # the sheet and invisible to anyone reading the terminal.
        print(f"  unreadable: {', '.join(result['unreadable'])}", file=sys.stderr)
    if out:
        local = RENDER.fetch(sheet, os.path.dirname(out) or ".", os.path.basename(out))
        print(f"  (local copy: {local})", file=sys.stderr)
