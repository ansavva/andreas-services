"""`convert`, `crop` and `composite`: Pillow work answered **synchronously**.

The second of the two questions the render-worker issue left open — *do `convert`
and `crop` belong on the queue at all?* — and the answer is no. `composite` joined
them later on the same test: several small images in, one plate out, still
sub-second, still nothing to stream.

Both are sub-second operations on a single image. A queue round trip is an
enqueue, a poll, and at least one more poll, so it costs more wall clock than the
work and buys nothing there is to buy: nothing to stream, no output large enough
to trouble a Lambda response, and no encode that could approach the 30-second
API Gateway ceiling. What it *would* cost is the ffmpeg image — 80 MB carried by
every request that will never touch it — which is why the split is drawn here and
not one module over.

So the API image carries **Pillow and not ffmpeg**. `media/imaging.py` is the
work; this is the addressing, the cap and the destination.

## All three of these copy. None modifies its source.

A run's output is append-only history, so a conversion and a crop are new nodes
beside the old one. That was true of the CLI commands these replace and it is the
reason `crop` exists at all: seventy-five images were once framed on a laptop and
uploaded, and the only record of what had been cut was gone. The box is stated,
recorded on the response, and the source is left alone.
"""

import logging
import os

from flask import Blueprint, g, jsonify

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ValidationError
from studio_core.media import imaging, mime
from studio_core.routes import support
from studio_core.services import catalog

logger = logging.getLogger(__name__)

bp = Blueprint("images", __name__, url_prefix="/api")


def _source(node_id) -> tuple[dict, bytes]:
    """The bytes behind a node, membership-checked and size-capped.

    The cap is checked against the **recorded size** before the object is read,
    so an oversized source costs one catalog read rather than a download the
    Lambda then has to survive. `get_body`'s own limit is the backstop for a row
    whose size was never written.
    """
    if not isinstance(node_id, str) or not node_id:
        raise ValidationError("node is required")
    record = catalog.node(node_id)
    support.member_of(record["lib"], support.memberships())
    if record.get("kind") != catalog.KIND_FILE or not record.get("blob_key"):
        raise ValidationError(f"{node_id} is not a file")
    cap = config.max_image_bytes()
    if int(record.get("size") or 0) > cap:
        raise ValidationError(
            f"that image is {record['size']} bytes and this route handles at most "
            f"{cap}. Large sources belong on the render queue.")
    return record, s3.get_body(record["blob_key"], cap)


def _sources(nodes) -> tuple[list[dict], list[bytes]]:
    """Several nodes, membership-checked, capped as ONE heap rather than each.

    `_source`'s cap is per image because `convert` and `crop` hold one. A plate
    holds all of its panels decoded at once plus the plate itself, so the budget
    that matters is the total — twelve images each just inside the per-image cap
    would be a third of a gigabyte of the Lambda's 512 MB before Pillow has
    drawn anything.
    """
    if not isinstance(nodes, list) or len(nodes) < 2:
        raise ValidationError(
            "nodes is a list of at least two node ids, in the order they lay out")
    if len(nodes) > imaging.MAX_PANELS:
        raise ValidationError(
            f"a plate holds at most {imaging.MAX_PANELS} panels — got {len(nodes)}. "
            "More than that is a contact sheet, which is a render job.")
    cap = config.max_image_bytes()
    records, bodies, spent = [], [], 0
    for node_id in nodes:
        record, data = _source(node_id)
        spent += len(data)
        if spent > cap:
            raise ValidationError(
                f"those {len(nodes)} images come to more than {cap} bytes together, "
                "which is what this route will hold at once. Compose fewer, or "
                "smaller ones.")
        records.append(record)
        bodies.append(data)
    return records, bodies


def _destination(body: dict, source: dict, target_ext: str) -> tuple[str, str]:
    """Where the new image lands, and what it is called. -> (folder node, name).

    Defaults to the source's own parent, which is what makes `--dest-key`
    optional: converting a frame in place beside itself is the common case and
    needs no folder to be named. The name defaults to the source's stem plus the
    new extension, and `create_numbered` in `support` resolves a clash — so
    converting twice lands `frame.png` and `frame (2).png` rather than a 409.
    """
    dest = body.get("dest") or source["parent_id"]
    folder = catalog.node(dest)
    support.member_of(folder["lib"], support.memberships())
    if folder.get("kind") != catalog.KIND_FOLDER:
        raise ValidationError(f"{dest} is not a folder")
    stem = os.path.splitext(source.get("name") or "image")[0]
    return folder["node_id"], body.get("name") or f"{stem}{target_ext}"


def _quality(body: dict) -> int:
    quality = body.get("quality", 95)
    if not isinstance(quality, int) or isinstance(quality, bool) or not 1 <= quality <= 100:
        raise ValidationError("quality must be between 1 and 100")
    return quality


def _target_ext(body: dict, source: dict) -> str:
    """`to` names a format; absent, the source's own is kept.

    Falls back to `.png` for a source whose extension Pillow cannot write —
    lossless, and accepted by every engine in the registry — rather than
    refusing: a `.gif` reference cropped to a face should come back as something
    usable, not as an error about GIF.
    """
    wanted = body.get("to")
    if wanted:
        if wanted not in imaging.EXT_FOR:
            raise ValidationError(f"cannot convert to '{wanted}'")
        return imaging.EXT_FOR[wanted]
    ext = os.path.splitext(source.get("name") or "")[1].lower()
    return ext if ext in imaging.PIL_FORMAT else ".png"


def _write(folder_id: str, name: str, data: bytes, target_ext: str) -> dict:
    node = catalog.create_numbered(folder_id, name, catalog.KIND_FILE)
    content_type = imaging.CONTENT_TYPE.get(target_ext) or mime.content_type_of(name)
    s3.put_text(node["blob_key"], data, content_type)
    metadata = s3.head(node["blob_key"])
    catalog.set_blob(node["node_id"], node["blob_key"],
                     size=metadata.get("ContentLength", len(data)),
                     content_type=content_type, checksum=s3.content_hash(metadata))
    return support.asset(node["node_id"])


@bp.post("/images/convert")
def convert_image():
    """Re-encode one image so an engine will accept it.

    Engines disagree about formats and the mismatch bites at the seam between
    them — GPT Image writes `.webp` by default and Kling accepts only
    `.jpg/.jpeg/.png` — so a still generated by one cannot be handed straight to
    the other as a start frame.

    **Which engine accepts what stays with the caller.** `--for kling` is a
    registry lookup and a decision, and the decision is "is a conversion needed
    at all"; a caller that finds the source already acceptable makes no request.
    Putting it here would mean this route answering "nothing to do" with a node
    id it did not create, which is a strange thing for a POST to do.
    """
    body = support.body()
    source, data = _source(body.get("node"))
    target_ext = _target_ext(body, source)
    folder_id, name = _destination(body, source, target_ext)

    converted = imaging.convert(data, target_ext, quality=_quality(body))
    logger.info("Converted %s -> %s in %s", source["node_id"], target_ext, g.library)
    return jsonify({"image": _write(folder_id, name, converted, target_ext),
                    "source": {"node": source["node_id"], "bytes": len(data)},
                    "bytes": len(converted)}), 201


@bp.post("/images/crop")
def crop_image():
    """Cut a rectangle out of an image. `box` is `LEFT,TOP,RIGHT,BOTTOM`.

    Source pixels, and the same order and meaning Pillow's `crop` takes and a
    detector reports. It is clamped to the image rather than refused — a box a
    few pixels past an edge is what padding a detection produces — and the
    response says whether that happened, because a silent clamp is a box that is
    not the box anybody stated.

    **Finding the subject is deliberately not here.** Face and body detection are
    platform work and a wrong box is worse than no command. Detect wherever you
    like; state the box.
    """
    body = support.body()
    source, data = _source(body.get("node"))
    target_ext = _target_ext(body, source)
    folder_id, name = _destination(body, source, target_ext)

    box = imaging.parse_box(body.get("box") if isinstance(body.get("box"), str)
                            else ",".join(str(v) for v in (body.get("box") or [])))
    cut, report = imaging.crop(data, box, target_ext, quality=_quality(body))
    logger.info("Cropped %s to %s in %s", source["node_id"], report["box"], g.library)
    return jsonify({"image": _write(folder_id, name, cut, target_ext),
                    "source": {"node": source["node_id"], "bytes": len(data)},
                    **report}), 201


@bp.post("/images/composite")
def composite_image():
    """Lay several images out as one plate. `nodes` is the order they appear in.

    **The operation that makes a multi-angle reference out of a turnaround.**
    Several engines take one image where the identity ought to be several — a
    front, a three-quarter and a back on one sheet carry a face and a build a
    single frontal view cannot, and they arrive in one reference slot.

    Panels are normalised to a common edge, **downscale only**: a panel smaller
    than its neighbours is the reason to shrink them, never to invent pixels for
    it. The gutter defaults to something visible and runs around the outside as
    well, because panels butted together on a shared white ground merge — two
    shoulders meet and one figure appears to have four arms.

    **Choosing the images and their order is deliberately not here**, for the
    reason detection is not in `crop`: which three angles carry a subject is a
    judgement about that subject, and a plate built from the wrong ones is worse
    than no plate. Name them, in order.
    """
    body = support.body()
    sources, bodies = _sources(body.get("nodes"))
    target_ext = _target_ext(body, sources[0])
    folder_id, name = _destination(body, sources[0], target_ext)
    if not body.get("name"):
        # `_destination`'s default is the source's own stem, which is right for
        # a conversion sitting beside its source and wrong here: a plate landing
        # in the same folder as its first panel under that panel's name would be
        # `create_numbered`'d to `front (2).png` and read as another angle.
        stem = os.path.splitext(sources[0].get("name") or "image")[0]
        name = f"{stem}-composite{target_ext}"

    plate, report = imaging.composite(
        bodies, target_ext,
        direction=body.get("direction") or "row",
        gap_percent=body.get("gap", imaging.DEFAULT_GAP_PERCENT),
        background=body.get("background") or "#ffffff",
        quality=_quality(body))
    logger.info("Composited %s panels into %sx%s in %s",
                len(bodies), report["width"], report["height"], g.library)
    return jsonify({"image": _write(folder_id, name, plate, target_ext),
                    "sources": [{"node": record["node_id"], "bytes": len(data)}
                                for record, data in zip(sources, bodies)],
                    **report}), 201
