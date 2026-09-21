"""Render jobs: enqueue here, do the work in the worker, report on a row.

`routes/scenes.py` and `routes/movies.py` both used to say this, and it is the
sentence this module exists to delete:

    **Stitching stays in the CLI.** `ffmpeg` ships in the pipeline wheel and the
    Lambda has none, so `assemble` downloads, stitches locally, uploads through
    `POST /api/scenes/<id>/output` and `PATCH`es the record. The API owns the
    record, not the encode.

It was sound reasoning about a fact — the API image had no `ffmpeg` — and a fact
about an image is a thing that can be changed. It is changed by a **second
image**, not by adding ffmpeg to the API's: a `-c copy` concat of a few clips
finishes in seconds, but any job needing a re-encode, or a long movie, exceeds
the 30-second API Gateway ceiling, and the image would grow ~80 MB for every
request that will never touch it.

## The shape

    caller ──► POST /api/renders ──► RENDER# row (queued) ──► SQS
                                                              │
                                       studio-prod-render ────┴──► worker
                                                                     │
                                    row: running ─► succeeded/failed ┘
                                    and, for an assemble, the scene or movie

The caller **polls the row** — `GET /api/renders/<id>` — which is the answer to
the first of the three questions the issue left open. Polling the *record* was
the obvious candidate and does not stretch: a scene and a movie carry a status,
and `frames grid` produces an image belonging to no scene, while a scene's
`error` is one field for every kind of failure a scene can have. So a job has a
row, and the row is what a poller watches. See `catalog.create_render`.

## What runs where, and why the split is not arbitrary

| | queue + render image | API image, synchronously |
|---|---|---|
| needs | `ffmpeg` **and** Pillow | Pillow only |
| jobs | `assemble`, `frame`, `grid`, `sheet` | `convert`, `crop` |
| bounded by | ephemeral disk and 15 minutes | one image, one round trip |

`convert` and `crop` are the second open question and the answer is no, they do
not belong on the queue: both are sub-second operations on a single image, so
enqueue-poll-poll costs more wall clock than the work. `routes/images.py`
answers them, and Pillow is 3 MB where ffmpeg is 80.

## What the worker does NOT do

**It resolves nothing.** A job's `parts` are node ids the caller already
resolved: `latest`, `#N`, "this scene is planned but not assembled", "this run
produced two videos, say which" are all refusals a person can act on, and they
belong in front of the person rather than at the far end of a queue where they
arrive as a failed job twenty seconds later. The CLI already does that
resolution and is tested for it.

**It appends to no chain and orders no cut.** `frames last --chain <slug>` and
`scenes add` are catalog writes on ids, so the caller makes them once the job
hands the node back. The worker's contract is: bytes in, one node out — except
for `assemble`, which owns the record it is cutting, because a cut that landed
in the bucket and never reached the scene is exactly the failure `SCENE_FIELDS`
was widened to fix.
"""

from __future__ import annotations

import json
import logging
import os

from botocore.exceptions import ClientError

from studio_core import config
from studio_core.clients.aws import s3, sqs
from studio_core.errors import ConfigError, NotFoundError, UpstreamError, ValidationError
from studio_core.media import mime
from studio_core.media import sheet as sheets
from studio_core.media import workspace
from studio_core.services import catalog, generate, keys

logger = logging.getLogger(__name__)

#: Cut an ordered list of clips into one file and record it on a scene or movie.
KIND_ASSEMBLE = "assemble"
#: One still frame out of one clip — the chaining handoff, and `frames at`.
KIND_FRAME = "frame"
#: A contact grid sampled across one clip, for looking at a video.
KIND_GRID = "grid"
#: A labelled grid of existing images — a character pool, or a scene's board.
KIND_SHEET = "sheet"
#: A still stored beside a media file, hidden, and linked — what a tile draws
#: so it need not load the file. Off a clip's first frame, or a still scaled
#: down; `catalog.link_poster` either way.
KIND_POSTER = "poster"
#: One clip rewritten in place with `moov` before `mdat`, so a browser can
#: start it before it has all of it. `media/faststart.py` has the measurement.
KIND_FASTSTART = "faststart"

KINDS = frozenset({KIND_ASSEMBLE, KIND_FRAME, KIND_GRID, KIND_SHEET, KIND_POSTER,
                   KIND_FASTSTART})

#: Tiles on a sheet, and frames in a grid. Bounds one image's memory: a sheet is
#: `cols × cell` wide and `rows × cell` tall in RGB, so 64 tiles at 300px is
#: ~50 MB decoded and 256 would be ~200 MB before anything is drawn into it.
MAX_TILES = 64

#: What `contact_grid` will sample. Above this the tiles are too small to read,
#: which is the only thing a grid is for.
MAX_GRID_FRAMES = 25


class RenderError(RuntimeError):
    """This job cannot succeed, and a redrive would fail it identically.

    The distinction the worker branches on. A `RenderError` — no video stream, a
    node that is not a file, a disk too small — closes the job `failed` and
    deletes the message. Anything else propagates, and SQS brings it back: a
    throttled DynamoDB write, a transient S3 refusal, a cold start that ran out
    of time.

    Getting this backwards in either direction is expensive. Redriving a
    permanent failure marches it to the dead-letter queue and puts a message
    there whose only remedy is a code change; swallowing a transient one loses
    work that would have succeeded on the next attempt.
    """


# ─────────────────────────────── enqueue ───────────────────────────────


def _folder(node_id: str) -> dict:
    record = catalog.node(node_id)
    if record.get("kind") != catalog.KIND_FOLDER:
        raise ValidationError(f"{node_id} is not a folder")
    return record


def _parts(raw, *, limit: int) -> list[dict]:
    """Validate the ordered list of inputs a job names. Order is the meaning."""
    if not isinstance(raw, list) or not raw:
        raise ValidationError("parts must be a non-empty list")
    if len(raw) > limit:
        raise ValidationError(
            f"a render may name at most {limit} inputs; this one names {len(raw)}")
    parts = []
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("node"), str):
            raise ValidationError("every part must be an object with a `node`")
        parts.append(entry)
    return parts


def _validated(kind: str, params: dict, lib: str) -> dict:
    """Refuse a job at the route rather than in the worker, wherever possible.

    **Everything checkable without moving bytes is checked here.** A job that
    fails validation twenty seconds later, in a worker, on a queue, reaches the
    person as a failed row with a sentence in it — where the same sentence on the
    `POST` reaches them as a 400 they can act on immediately. What cannot be
    checked here is anything about the *content* of a file, which is why
    `media/ffmpeg.py` still raises.
    """
    if kind not in KINDS:
        raise ValidationError(f"'{kind}' is not a render kind")
    limit = config.max_render_inputs()

    if kind == KIND_ASSEMBLE:
        target = params.get("target")
        if not isinstance(target, str):
            raise ValidationError("assemble needs a `target` scene or movie id")
        # The kind first, then the read. `entity_kind` refuses anything that is
        # not an entity id at all (`node-…`, a name) with a 400 naming it, and
        # asking a run for a cut is a 400 rather than a wasted catalog read.
        kind = catalog.entity_kind(target)
        if kind not in (catalog.ENTITY_SCENE, catalog.ENTITY_MOVIE):
            raise ValidationError("only a scene or a movie can be assembled")
        record = catalog.entity(kind, target)
        if record["lib"] != lib:
            # A 404 rather than a 403: an entity id is shareable, so a caller may
            # hold one that is not theirs, and "there is no such scene here" is
            # the whole of what they are owed.
            raise NotFoundError(target)
        clean = {"target": target, "parts": _parts(params.get("parts"), limit=limit)}
        characters = params.get("characters")
        if characters is not None:
            if not isinstance(characters, list):
                raise ValidationError("characters must be a list of character ids")
            clean["characters"] = characters
        return clean

    if kind == KIND_POSTER:
        node = params.get("node")
        if not isinstance(node, str):
            raise ValidationError("poster needs a `node` naming one image or video")
        return {"node": node}

    if kind == KIND_FASTSTART:
        node = params.get("node")
        if not isinstance(node, str):
            raise ValidationError("faststart needs a `node` naming one video")
        return {"node": node}

    if kind in (KIND_FRAME, KIND_GRID):
        node = params.get("node")
        if not isinstance(node, str):
            raise ValidationError(f"{kind} needs a `node` naming one video")
        # **The scalars first, then the folder read.** Both orders refuse the same
        # requests; this one refuses a malformed `at` without a catalog round
        # trip, and reports the field a caller can fix rather than a 404 about a
        # destination they got right.
        clean = {"node": node, "name": params.get("name") or ""}
        if kind == KIND_FRAME:
            at, from_end = params.get("at"), params.get("from_end")
            if at is None and from_end is None:
                raise ValidationError("frame needs `at` or `from_end`")
            if at is not None and from_end is not None:
                raise ValidationError("frame takes `at` or `from_end`, not both")
            for label, value in (("at", at), ("from_end", from_end)):
                if value is not None and (not isinstance(value, (int, float))
                                          or isinstance(value, bool) or value < 0):
                    raise ValidationError(f"{label} must be a non-negative number")
            clean["at"], clean["from_end"] = at, from_end
        else:
            # `params.get("count") or 4` turned an explicit `0` into 4 — a
            # refusal silently becoming a default is worse than either.
            count = 4 if params.get("count") is None else params.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_GRID_FRAMES:
                raise ValidationError(f"count must be between 1 and {MAX_GRID_FRAMES}")
            clean["count"] = count
        clean["dest"] = _folder(params.get("dest") or "")["node_id"]
        return clean

    tiles = _parts(params.get("parts"), limit=min(limit, MAX_TILES))
    cols, cell = params.get("cols") or 5, params.get("cell") or 300
    for label, value, top in (("cols", cols, 12), ("cell", cell, 1000)):
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= top:
            raise ValidationError(f"{label} must be between 1 and {top}")
    return {"parts": tiles, "cols": cols, "cell": cell,
            "dest": _folder(params.get("dest") or "")["node_id"],
            "name": params.get("name") or "sheet.png"}


def enqueue(lib: str, kind: str, params: dict) -> dict:
    """Validate, write the row, put the message on the queue. -> the row.

    **The row is written first.** A worker cannot be handed a job whose row does
    not exist yet, and the opposite ordering has a genuine race: SQS delivers
    faster than DynamoDB's read-after-write on a different partition is worth
    relying on. What this order costs is the other failure — a row written and a
    `SendMessage` that throws — which leaves a job `queued` for ever. That is
    visible to the poller and spends nothing, where the other is a worker
    reporting on a job nobody can find.

    The message carries **the render id and nothing else**. Copying the params
    into it would be a second copy of the job that a redrive could disagree with;
    the worker reads the row, which is the one that is true.
    """
    queue = config.render_queue_url()
    if not queue:
        raise ConfigError(
            "This environment has no render queue — STUDIO_RENDER_QUEUE_URL is unset. "
            "Prod and a per-machine dev stack both set it; CI deliberately does not.")

    clean = _validated(kind, params if isinstance(params, dict) else {}, lib)
    record = catalog.create_render(lib, kind, clean)
    try:
        sqs.send(queue, json.dumps({"render": record["id"]}))
    except (ClientError, UpstreamError) as exc:
        # Say so on the row rather than leaving it `queued` for ever. The 502
        # still goes back to the caller; this is for the caller who already had
        # the id from a retry and is polling it.
        catalog.update_render(record["id"], status="failed",
                              error=f"could not enqueue: {exc}")
        raise UpstreamError("Could not enqueue the render") from exc
    logger.info("Queued render %s (%s) for %s", record["id"], kind, lib)
    return record


#: The kinds of file a tile draws, and so the kinds that get a poster.
POSTER_KINDS = frozenset({"image", "video"})


def wants_poster(record: dict) -> bool:
    """Whether this node is one a tile would draw and a poster would serve.

    A media file with bytes behind it and no poster yet. Not a poster itself
    — `poster_of` is the derivative's own mark, and a poster of a poster is
    the recursion the sweep must never start — and not a placeholder upload
    whose bytes never came.
    """
    if record.get("kind") != catalog.KIND_FILE or not record.get("blob_key"):
        return False
    if record.get("poster") or record.get("poster_of"):
        return False
    if "size" not in record:
        return False  # `browse.is_abandoned_upload`: a key promised, no bytes
    return keys.kind(record.get("name") or "") in POSTER_KINDS


def queue_poster(lib: str, node_id: str) -> bool:
    """Ask the worker for a still for one node. **Best effort, by contract.**

    Every caller is on a path that has just stored something a person asked
    for — a run closing, an upload confirmed, a frame grabbed — and none of
    them may fail because a poster could not be queued: a stack with no render
    queue (a dev machine that has not provisioned one), or SQS refusing, is a
    poster missing — the tile draws the original, as every tile did before
    posters — and never a run that fails to close or an upload that reports a
    failure over bytes that landed. Returns whether a job was queued.
    """
    try:
        enqueue(lib, KIND_POSTER, {"node": node_id})
    except Exception as exc:  # noqa: BLE001 — see the docstring
        logger.warning("No poster queued for %s: %s", node_id, exc)
        return False
    return True


def wants_faststart(record: dict) -> bool:
    """Whether this node is a clip nobody has yet checked for atom order.

    An MP4 with bytes behind it and no `faststart` mark. The mark is written
    at ingest and by the worker's job whichever way the check went, so a
    sweep re-reads nothing it has already answered.
    """
    if record.get("kind") != catalog.KIND_FILE or not record.get("blob_key"):
        return False
    if record.get("faststart") or record.get("poster_of") or "size" not in record:
        return False
    from studio_core.media import faststart
    return faststart.is_mp4_name(record.get("name") or "")


def queue_faststart(lib: str, node_id: str) -> bool:
    """Ask the worker to index one clip. Best effort — see `queue_poster`."""
    try:
        enqueue(lib, KIND_FASTSTART, {"node": node_id})
    except Exception as exc:  # noqa: BLE001 — see `queue_poster`
        logger.warning("No faststart queued for %s: %s", node_id, exc)
        return False
    return True


def _require_queue() -> None:
    if not config.render_queue_url():
        # Refused once, up front, rather than swallowed per row by
        # `queue_poster` — a person asked for this sweep and is owed the
        # sentence, not two thousand warnings in a log.
        raise ConfigError(
            "This environment has no render queue — STUDIO_RENDER_QUEUE_URL is unset. "
            "Prod and a per-machine dev stack both set it; CI deliberately does not.")


def _sweep(lib: str, wants, queue) -> dict:
    """Walk `by-recent` — exactly the images and videos, nothing else — and
    queue one job per record `wants` says so for. Returns what it queued and
    what it passed over; nothing here waits for the worker."""
    _require_queue()
    records, truncated = catalog.recent(lib, config.max_poster_sweep())
    queued, skipped = [], 0
    for record in records:
        if not wants(record):
            skipped += 1
            continue
        if queue(lib, record["node_id"]):
            queued.append(record["node_id"])
    return {"queued": queued, "skipped": skipped, "truncated": truncated}


def sweep_posters(lib: str) -> dict:
    """Queue a poster for every media file in a library that has none.

    **The backfill**, and idempotent: a node already covered is a read, not a
    job, so this is safe to run over a whole library as often as wanted.
    """
    return _sweep(lib, wants_poster, queue_poster)


def sweep_faststart(lib: str) -> dict:
    """Queue a faststart check for every clip in a library not yet marked.

    The clip half of the backfill. Each job is a few dozen bytes of ranged
    reads when the clip is already in order and a rewrite when it is not,
    and either way the row is marked so the next sweep skips it.
    """
    return _sweep(lib, wants_faststart, queue_faststart)


def wants_retype(record: dict) -> str | None:
    """The content type this media row should carry and does not — or None.

    A row in `by-recent` is an image or a video by its extension (`keys.kind`
    put it there), so a `content_type` on it that names neither is wrong,
    however it got there: `application/octet-stream` off a MIME table
    without `.webp`, or nothing at all. What it should say is what the
    extension says, the same table `mime.content_type_of` uses at ingest.
    """
    if not record.get("blob_key"):
        return None
    if mime.served_type(record.get("content_type")):
        return None
    wanted = mime.content_type_of(record.get("name") or "")
    return wanted if mime.served_type(wanted) else None


def sweep_content_types(lib: str) -> dict:
    """Retype every media file in a library whose row says it is not media.

    **The backfill for `media/mime.py`**, and the one sweep that does its
    work here rather than queueing it: a retype is one server-side copy and
    one row write, against tens of rows, where a poster is an ffmpeg job
    against thousands. Both the object and the row are rewritten, so a
    reader off either — a tile's `<img>`, the run feed's `isPromotable` —
    sees the same type. Idempotent: a row already typed is passed over.
    """
    records, truncated = catalog.recent(lib, config.max_poster_sweep())
    retyped, skipped = [], 0
    for record in records:
        wanted = wants_retype(record)
        if not wanted:
            skipped += 1
            continue
        try:
            s3.retype(record["blob_key"], wanted)
        except NotFoundError:
            # A row whose bytes are gone is a different problem, and not one
            # a sweep over content types should fail on.
            skipped += 1
            continue
        catalog.set_blob(record["node_id"], record["blob_key"], content_type=wanted)
        retyped.append(record["node_id"])
    return {"retyped": retyped, "skipped": skipped, "truncated": truncated}


# ─────────────────────────────── the worker ───────────────────────────────


def handle(raw_body: str) -> dict | None:
    """One SQS message body. **Idempotent** — a terminal job is returned untouched.

    Shaped like `services/callbacks.handle` on purpose: both are drained by a
    Lambda in prod and by a process on a laptop in dev, and a reader who knows
    one knows the other. A message naming a job that does not exist is dropped
    rather than redriven — a deleted library is the ordinary way to reach it, and
    there is nothing to retry toward.
    """
    try:
        message = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RenderError(f"queue message is not JSON: {exc}") from exc
    if not isinstance(message, dict) or not isinstance(message.get("render"), str):
        raise RenderError("queue message names no render")
    return run(message["render"])


def run(render_id: str) -> dict:
    """Do one job and report on its row, whichever way it goes."""
    try:
        job = catalog.render(render_id)
    except NotFoundError as exc:
        raise RenderError(f"render {render_id} does not exist") from exc

    if job["status"] in catalog.TERMINAL_RENDER_STATUSES:
        # At-least-once delivery is ordinary traffic. Re-running an assemble
        # would cut the scene a second time and push a perfectly good cut into
        # `cuts` for no reason, so the guard is here rather than left to the
        # jobs to each be idempotent about.
        logger.info("Render %s is already %s; nothing to do", render_id, job["status"])
        return job

    catalog.update_render(render_id, status="running")
    try:
        result = _dispatch(job)
    except (RenderError, workspace.OutOfSpace, ValidationError,
            # **A vanished object is permanent, not transient.** `s3.download`
            # raises `NotFoundError` for a node whose blob was deleted out from
            # under the job, and no number of redrives will put it back — where
            # a throttle or a refused connection is exactly what the queue is
            # for. Getting this one wrong marches a job to the dead-letter queue
            # over a file somebody deliberately removed.
            NotFoundError) as refusal:
        logger.warning("Render %s failed: %s", render_id, refusal)
        return catalog.update_render(render_id, status="failed", error=str(refusal))
    except Exception:
        # Transient by assumption — the queue brings it back, and the row is left
        # `running` so a poller sees it move rather than seeing a lie.
        logger.exception("Render %s raised; leaving it on the queue", render_id)
        raise
    return catalog.update_render(render_id, status="succeeded", result=result)


def _dispatch(job: dict) -> dict:
    kind, params = job["kind"], job.get("params") or {}
    if kind == KIND_ASSEMBLE:
        return _assemble(job["lib"], params)
    if kind == KIND_FRAME:
        return _frame(params)
    if kind == KIND_POSTER:
        return _poster(params)
    if kind == KIND_FASTSTART:
        return _faststart(params)
    if kind == KIND_GRID:
        return _grid(params)
    if kind == KIND_SHEET:
        return _sheet(params)
    raise RenderError(f"'{kind}' is not a render kind this worker knows")


# ─────────────────────────── moving bytes about ───────────────────────────


def _blob(node_id: str) -> dict:
    """A file node with bytes behind it, or a refusal naming which half is missing."""
    try:
        record = catalog.node(node_id)
    except NotFoundError as exc:
        raise RenderError(f"{node_id} does not exist") from exc
    if record.get("kind") != catalog.KIND_FILE:
        raise RenderError(f"{node_id} is a folder, not a file")
    if not record.get("blob_key"):
        raise RenderError(f"{node_id} has no bytes behind it")
    return record


def _pull(space: workspace.Workspace, node_id: str, local_name: str) -> str:
    record = _blob(node_id)
    path = space.at(local_name)
    s3.download(record["blob_key"], path)
    return path


def _store(dest_folder: str, name: str, path: str, *, poster: bool = True) -> dict:
    """Put a produced file in the library under `dest_folder`. -> an asset pointer.

    **`create_numbered`, not `create_node`**, for the reason
    `generate._store_output` gives: a name clash is a `ConflictError`, and a job
    that is retried after storing something would then fail identically for ever
    on a filename. The numbered form lands `sheet (2).png` beside a stray from
    the first attempt — one tidyable orphan instead of a job that can never
    finish.

    **What lands here gets a poster queued, like any other media file** — a
    grabbed frame, a contact grid and a sheet are all drawn in tiles. `poster=
    False` is for the one job whose output IS a poster.
    """
    content_type = mime.content_type_of(name)
    node = catalog.create_numbered(dest_folder, name, catalog.KIND_FILE)
    s3.put_file(node["blob_key"], path, content_type)
    metadata = s3.head(node["blob_key"])
    stored = catalog.set_blob(node["node_id"], node["blob_key"],
                              size=metadata.get("ContentLength", 0),
                              content_type=metadata.get("ContentType") or content_type,
                              checksum=s3.content_hash(metadata))
    if poster and wants_poster(stored):
        queue_poster(stored["lib"], node["node_id"])
    return {"node": node["node_id"], "name": node["name"],
            "size": metadata.get("ContentLength", 0), "content_type": content_type}


def _declared(parts: list[dict]) -> int:
    """How many bytes this job's inputs add up to, off the catalog.

    Read from the rows rather than measured, so `workspace.reserve` can refuse a
    job **before** the first download instead of after the last one that fits.
    A row with no `size` counts as zero and the guard is correspondingly weaker;
    that is the honest failure — a node written before sizes were recorded — and
    it is preferable to refusing the job outright.
    """
    found = catalog.records([part["node"] for part in parts])
    return sum(int(record.get("size") or 0) for record in found.values())


# ─────────────────────────────── the jobs ───────────────────────────────


def _assemble(lib: str, params: dict) -> dict:
    """Cut the parts into one file and record it on the scene or the movie.

    **The one job that owns a record**, because a cut that reached the bucket and
    never reached the scene is the exact failure the widening of `SCENE_FIELDS`
    was written for: the encode had happened, the file was there, and the scene
    did not know it had one.

    Each part is copied into the target's own folder as well as being stitched,
    which is what `domain/scenes.py` and `domain/movies.py` both did and for the
    reason they both gave: a scene stays playable and re-cuttable while its runs
    are rebuilt around it. It is a download plus an upload rather than a
    server-side copy because a second node on one blob is copy-on-write, and the
    API's delete route destroys the shared bytes when either row goes. The file
    is already local from the download, so the cost is one PUT per part.
    """
    from studio_core.media import ffmpeg

    target = params["target"]
    kind = catalog.entity_kind(target)
    record = catalog.entity(kind, target)
    if record["lib"] != lib:
        raise RenderError(f"{target} is not in {lib}")

    is_scene = kind == catalog.ENTITY_SCENE
    child_folder, label, stem = (
        ("shots", "shots", "shot") if is_scene else ("scenes", "scenes", "scene"))
    parts = params["parts"]

    with workspace.Workspace(prefix="assemble-") as space:
        space.reserve(_declared(parts))

        folder = _child_folder(record["folder"], child_folder)
        local: list[str] = []
        for n, part in enumerate(parts, 1):
            source = _blob(part["node"])
            ext = os.path.splitext(source.get("name") or "")[1] or ".mp4"
            path = _pull(space, part["node"], f"{stem}-{n:02d}{ext}")
            local.append(path)
            copied = _store(folder["node_id"], f"{stem}-{n:02d}{ext}", path)
            part["n"] = n
            part["copy"] = copied["node"]

        stem = generate.slugify(record.get("name") or "") or record["id"]
        out_local = space.at("cut", f"{stem}.mp4")
        info = ffmpeg.stitch(local, out_local, label=label)
        for part, probe in zip(parts, info.pop("probes")):
            part["duration"] = probe["duration"]

        # A NEW node per cut, so the one before it stays reachable. Numbered from
        # what the record already holds rather than from the folder: the record
        # is what `cuts` is read off, and a stray file in the folder must not be
        # able to renumber a history that does not include it.
        superseded = catalog.output_node(record)
        take = len(record.get("cuts") or []) + (1 if superseded else 0) + 1
        name = f"{stem}.mp4" if take == 1 else f"{stem}-{take}.mp4"
        output = _store(_child_folder(record["folder"], "output")["node_id"],
                        name, out_local)
        probe = ffmpeg.probe(out_local)

    info["cuts"] = [{"n": part["n"], "node": part["copy"],
                     "duration": part.get("duration"),
                     **{k: part[k] for k in ("run", "scene", "name") if k in part}}
                    for part in parts]

    assignments = {
        "output": {"node": output["node"], **probe},
        "stitch": info,
        "cuts": catalog.keep_cut(record, output["node"]),
        "assembled": catalog.now(),
        "status": "assembled",
    }
    if params.get("characters") is not None:
        assignments["characters"] = sorted(set(params["characters"]))
    record = catalog.update_project_entity(
        kind, record, assignments, {"status": "assembled", "thumb": output["node"]})

    return {"output": output, "stitch": info, "target": target,
            # Named rather than left to be inferred from the method string. It is
            # the thing the stitching contract exists to make visible, and a
            # boolean is what a caller can branch on.
            "re_encoded": not info.get(f"uniform_{label}", True)}


def _child_folder(parent_id: str, name: str) -> dict:
    """A conventional subfolder, made if it is absent. `layout.folder_under`'s rule.

    Imported lazily rather than at module scope only because `services/layout.py`
    is the thinnest possible module and this is its one caller outside a route;
    the indirection is here so the convention has one implementation.
    """
    from studio_core.services import layout

    return layout.folder_under(parent_id, name)


def _frame(params: dict) -> dict:
    """One still out of one clip — the chaining handoff, and `frames at`."""
    from studio_core.media import ffmpeg

    with workspace.Workspace(prefix="frame-") as space:
        # factor=1: the output of a frame grab is a PNG, whatever the clip weighs.
        space.reserve(_declared([{"node": params["node"]}]), factor=1)
        source = _pull(space, params["node"], "source" + _ext(params["node"]))
        name = params.get("name") or "frame.png"
        local = ffmpeg.grab(source, params.get("at"),
                            space.at("out", name), from_end=params.get("from_end"))
        return {"frame": _store(params["dest"], name, local)}


def _poster(params: dict) -> dict:
    """A small still beside one media file, linked as its poster.

    Off a clip's first frame, or a still scaled down to the same width — one
    job, because one tile draws both and the tile is what this is for. What
    a still's poster saves is `media/imaging.poster`'s measurement; what a
    clip's saves is `media/faststart.py`'s.

    **Idempotent, and cheaply so.** A file that already points at a still
    that exists is answered from the row without pulling the file — the
    backfill runs this over whole libraries, and a second pass must cost
    reads, not renders. `ffmpeg.duration` is read while a clip is on disk,
    because the tile that draws the poster no longer loads the metadata the
    badge used to come from.

    Stored in the file's own folder rather than a `derived/` beside it:
    `poster_of` keeps it out of every listing, so there is nothing for a
    folder to organise, and a file moved or copied is not separated from a
    sibling folder it never knew about.

    **A poster never gets a poster.** The derivative carries `poster_of`, and
    a job naming one is refused for good rather than left to recurse.
    """
    from studio_core.media import ffmpeg, imaging

    source_node = _blob(params["node"])
    if source_node.get("poster_of"):
        raise RenderError(f"{source_node['node_id']} is a poster already")
    if source_node.get("poster"):
        existing = catalog.records([source_node["poster"]]).get(source_node["poster"])
        if existing and existing.get("blob_key"):
            return {"poster": {"node": existing["node_id"], "name": existing["name"]},
                    "existing": True}

    kind = keys.kind(source_node.get("name") or "")
    if kind not in POSTER_KINDS:
        raise RenderError(f"{source_node['node_id']} is not an image or a video")

    seconds = None
    with workspace.Workspace(prefix="poster-") as space:
        space.reserve(_declared([{"node": source_node["node_id"]}]), factor=1)
        source = _pull(space, source_node["node_id"], "source" + _ext(source_node["node_id"]))
        stem = os.path.splitext(source_node["name"])[0]
        if kind == "video":
            seconds = ffmpeg.duration(source)
            local = ffmpeg.poster(source, space.at("out", f"{stem}.poster.jpg"))
        else:
            local = imaging.poster(source, space.at("out", f"{stem}.poster"))
        stored = _store(source_node["parent_id"], os.path.basename(local), local,
                        poster=False)
    catalog.link_poster(source_node["node_id"], stored["node"], duration=seconds)
    result = {"poster": stored}
    if seconds is not None:
        result["duration"] = seconds
    return result


def _faststart(params: dict) -> dict:
    """Move one clip's `moov` in front of its `mdat`, in place, on the worker.

    **The check costs bytes, not the clip.** `needs_faststart_at` walks the
    top-level atoms through ranged reads, and for a clip already in order —
    every output stored since ingest started doing this — the job is two
    small GETs and a marker write. Only a clip that needs it is pulled,
    rewritten (`media/faststart.py`: same bytes, different order) and put
    back under the same key, so the node keeps its id, name and place; `size`
    is unchanged and `checksum` is re-read off the new object.

    The route `POST /api/nodes/<id>/faststart` does the same thing
    synchronously for one clip a person names; this is what a library sweep
    queues, and what an upload of an MP4 queues as it is confirmed.
    """
    from studio_core.media import faststart

    clip = _blob(params["node"])
    if not faststart.is_mp4_name(clip.get("name") or ""):
        raise RenderError(f"{clip['node_id']} is not an MP4")
    key = clip["blob_key"]
    total = int(clip.get("size") or 0) or int(s3.head(key).get("ContentLength", 0))

    def read(offset: int, length: int) -> bytes:
        return s3.read_range(key, offset, min(offset + length, total) - 1)

    if not faststart.needs_faststart_at(read, total):
        catalog.set_blob(clip["node_id"], key, faststart=True)
        return {"rewritten": False}

    with workspace.Workspace(prefix="faststart-") as space:
        space.reserve(_declared([{"node": clip["node_id"]}]), factor=2)
        local = _pull(space, clip["node_id"], "source.mp4")
        rewritten = faststart.faststart(local)
        if rewritten:
            s3.put_file(key, local, clip.get("content_type") or "video/mp4")
    metadata = s3.head(key)
    catalog.set_blob(clip["node_id"], key,
                     size=metadata.get("ContentLength", 0),
                     content_type=metadata.get("ContentType") or clip.get("content_type"),
                     checksum=s3.content_hash(metadata),
                     faststart=True)
    return {"rewritten": rewritten}


def _grid(params: dict) -> dict:
    """A contact sheet sampled across one clip. **The only way to read a video.**

    A generated clip has to be looked at before more money is spent on top of it,
    and a video cannot be read the way an image can — including by an agent,
    which otherwise has no way to check its own output.
    """
    from studio_core.media import ffmpeg

    with workspace.Workspace(prefix="grid-") as space:
        space.reserve(_declared([{"node": params["node"]}]), factor=1)
        source = _pull(space, params["node"], "source" + _ext(params["node"]))
        name = params.get("name") or "grid.jpg"
        out = space.at("out", name)
        times = ffmpeg.contact_grid(source, params["count"], out)
        return {"grid": _store(params["dest"], name, out),
                "sampled_at": [round(t, 2) for t in times]}


def _sheet(params: dict) -> dict:
    """A labelled grid of images that already exist. Pillow only, no ffmpeg.

    On the queue rather than in the API despite needing no ffmpeg, because the
    bounded thing here is not the encode: it is N downloads, and N is a character
    pool. Fifty-four stills is the size of the published dev fixture.
    """
    parts = params["parts"]
    with workspace.Workspace(prefix="sheet-") as space:
        space.reserve(_declared(parts), factor=1)
        paths, captions = [], []
        for n, part in enumerate(parts, 1):
            source = _blob(part["node"])
            ext = os.path.splitext(source.get("name") or "")[1].lower() or ".png"
            if ext not in sheets.IMG_EXTS:
                raise RenderError(f"{source.get('name') or part['node']} is not an image")
            paths.append(_pull(space, part["node"], f"tile-{n:03d}{ext}"))
            # **Given captions are authoritative and the order is left alone.**
            # For a payload review tile N is the image a prompt cites as
            # `[ImageN]`, so natural-sorting them would renumber the citation.
            captions.append(part.get("caption") or os.path.splitext(
                source.get("name") or f"{n}")[0])
        name = params["name"]
        out = space.at("out", name)
        report = sheets.build(paths, out, params["cols"], params["cell"],
                              captions=captions)
        return {"sheet": _store(params["dest"], name, out), **report}


def _ext(node_id: str) -> str:
    """The source file's extension, which ffmpeg uses to pick a demuxer."""
    name = catalog.node(node_id).get("name") or ""
    return os.path.splitext(name)[1] or ".mp4"
