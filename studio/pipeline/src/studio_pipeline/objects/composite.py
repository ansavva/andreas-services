"""`studio composite` — lay several images out as one multi-angle plate.

**The reference trick the pipeline had no verb for.** Several engines take ONE
image where identity wants several: a start frame, a single `image` field, a
reference slot already spent on something else. A front, a three-quarter and a
back laid side by side on one sheet carry a face AND a build that a single
frontal view cannot — and they arrive in one slot.

A character's turnaround is already the raw material. The standard set renders
eight face angles and six body ones; three of them composited is a plate, and
the plate is a node in the character's tree like any other image, described and
tagged beside the panels it was made from.

  # three angles of one wardrobe, into the folder they came from
  studio composite --key <node> --key <node> --key <node> \
      --dest-key characters/<name>/reference/wardrobe/<outfit>/<file>.png

  # a column instead of a row, on a grey ground
  studio composite --key <node> --key <node> --direction column \
      --background '#f2f2f2' --add-input <project>

**Order is the option order**, left to right in a row and top to bottom in a
column. There is no sorting and no detection: which angles carry a subject is a
judgement about that subject, and a plate built from the wrong three is worse
than no plate. `studio character images <name>` is how you find them.

THE PIXELS ARE PUSHED AROUND BY THE SERVICE, SYNCHRONOUSLY
-----------------------------------------------------------
One `POST /api/images/composite`, for the reason `studio crop` is one: Pillow
lives in the API image and not in this wheel, so the panels never come down and
the plate never goes back up. It is not on the render queue either — laying a
handful of images out is sub-second, and an enqueue plus two polls would cost
more wall clock than the work.

WHAT THE GEOMETRY DOES, AND WHY IT IS PRINTED
-----------------------------------------------------------
**Panels are normalised to a common edge — downscale only.** The shortest panel
sets a row's height and the narrowest sets a column's width. A panel smaller
than its neighbours is the reason to shrink them, never to invent pixels for it:
a genuine render beside an upscaled one reads as two subjects.

**The gutter is not decoration.** Panels butted edge to edge on a shared white
ground merge — two shoulders meet, and one figure appears to have four arms.
`--gap` is a percentage of the panel edge rather than a pixel count so that it
survives a change of source resolution, it defaults to 6, and it runs around the
outside as well so no figure sits against the sheet's edge.

Both are reported on stderr, because a plate that was silently rescaled is a
plate nobody stated.
"""
from __future__ import annotations

import sys

import click

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.errors import die, reports
from studio_pipeline.objects.convert import destination


@click.command(help=__doc__)
@click.option("--add-input", help="Write into PROJECT's input pool.")
@click.option("--background", default="#ffffff",
              help="Hex colour behind the panels (default #ffffff).")
@click.option("--dest-key", help="Explicit destination name path instead.")
@click.option("--direction", type=click.Choice(["row", "column"]), default="row",
              help="Lay the panels across or down (default row).")
@click.option("--gap", type=int, default=6,
              help="Gutter and outer margin, as a % of the panel edge (default 6).")
@click.option("--key", "keys", multiple=True,
              help="A panel, by node id or name path. Repeat, in layout order.")
@click.option("--quality", type=int, default=95, help="JPEG/WebP quality (default 95).")
@click.option("--to", type=click.Choice(["jpeg", "jpg", "png", "webp"]),
              help="Output format (default: the first panel's).")
# The route reads every panel, so a mistyped one arrives as an `api.NotFound`
# carrying the path, and a plate of one image or of thirty as an `api.ApiError`.
# Without this the commonest failures of this command reach a person as a
# traceback instead of the sentence the route wrote.
@reports(api.NotFound, api.Forbidden, api.ApiError)
def composite(add_input, background, dest_key, direction, gap, keys, quality, to):
    if not add_input and not dest_key:
        die("choose a destination: --add-input PROJECT or --dest-key KEY.")
    if len(keys) < 2:
        die(f"a plate takes at least two panels — got {len(keys)}. "
            "Repeat --key once per angle, in the order they should lay out.")

    # A `--key` may be a node id or a name path; the route takes nodes, because
    # a node is the one address a rename cannot invalidate.
    nodes = [k if k.startswith("node-") else store.resolve(k)["id"] for k in keys]
    folder, name = destination(add_input, dest_key)
    reply = entities.composite_image(nodes, direction=direction, gap=gap,
                                     background=background, to=to,
                                     dest=folder, name=name, quality=quality)

    print(reply["image"]["node"])
    sizes = " + ".join(f"{p['width']}x{p['height']}" for p in reply["panels"])
    # **The rescale is reported for the reason `crop` reports its clamp.** A
    # panel that came in at a different size and went out matching its
    # neighbours is a thing that happened to somebody's image without being
    # asked for, and the sheet does not show it.
    note = "" if not reply["scaled"] else " (panels rescaled to a common edge)"
    print(f"composited {len(nodes)} panels as a {reply['direction']}: {sizes} "
          f"-> {reply['width']}x{reply['height']}, gutter {reply['gap']}px"
          f"{note}; sources untouched", file=sys.stderr)
    return 0
