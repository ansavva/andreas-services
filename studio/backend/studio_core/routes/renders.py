"""Render jobs: `POST` one, `GET` it until it stops moving.

The polling surface. `services/render.py` argues the design; this is two routes
and the membership check between them.

**Why a caller polls a job row rather than the scene.** The issue that moved
ffmpeg into the service proposed polling the record, since a scene and a movie
already carry a status. That is right for an assemble and does not reach:
`frames grid` produces an image belonging to no scene, and a scene's `error` is
one field for every kind of failure a scene can have — so a poller watching it
cannot tell "this cut failed" from "the last plan revision was refused". A job
row says what this job did.

**`GET` is membership-checked and not merely unguessable.** A render id is a v4
UUID, which is a fine thing to hand out and a poor thing to authorise with. The
row carries the library it was created in and the caller has to be in it.

There is no listing route, and `catalog.create_render` says why: nothing walks
these rows, and the thing that reports on a job that never finished is the
dead-letter alarm in `modules/render`. A `GET /api/renders` would need a second
row per job to be answerable at all.
"""

import logging

from flask import Blueprint, g, jsonify

from studio_core.routes import support
from studio_core.services import catalog, render

logger = logging.getLogger(__name__)

bp = Blueprint("renders", __name__, url_prefix="/api")


def _job(render_id: str) -> dict:
    record = catalog.render(render_id)
    support.member_of(record["lib"], support.memberships())
    return record


@bp.post("/renders")
def create_render():
    """Enqueue one job. **202, and the body is the row to poll.**

    Not 201: nothing has been created that the caller asked for — the scene has
    no new cut and the folder has no new image. What exists is an accepted
    request, which is exactly what 202 means, and the `Location` points at the
    thing that will eventually say how it went.
    """
    body = support.body()
    support.member_of(g.library, support.memberships())
    record = render.enqueue(g.library, body.get("kind") or "", body.get("params") or {})
    return jsonify(record), 202, {"Location": f"/api/renders/{record['id']}"}


@bp.post("/posters")
def sweep_posters():
    """Queue a poster for every image and video in the library that has none.

    **The backfill**, and the one listing-shaped write here. New files get a
    poster as they land — a run closing, an upload confirmed, a frame grabbed
    — and this is for everything stored before the service did that, or on a
    stack whose queue was down when it did. Idempotent: a file already
    covered is passed over, so it is safe to call as often as wanted.

    202, like `create_render`: what exists afterwards is a queue of accepted
    jobs, and the tiles pick the stills up on their next listing. The body
    says how many were queued and whether the walk reached the end of the
    library (`config.max_poster_sweep`).
    """
    support.member_of(g.library, support.memberships())
    report = render.sweep_posters(g.library)
    return jsonify(report), 202


@bp.post("/faststarts")
def sweep_faststart():
    """Queue a faststart check for every clip in the library not yet marked.

    The clip half of the backfill `sweep_posters` is the picture half of:
    every clip stored before ingest began indexing them, and every upload.
    Cheap to repeat — a clip already in order is a few bytes of ranged reads
    and a marker, and a marked one is skipped without a read.
    """
    support.member_of(g.library, support.memberships())
    report = render.sweep_faststart(g.library)
    return jsonify(report), 202


@bp.post("/content-types")
def sweep_content_types():
    """Retype every media file whose row says it is not media, in place.

    The third backfill, and the one that answers 200 rather than 202: a
    retype is a server-side copy and a row write, so it is done by the time
    the body says which rows it touched. `render.sweep_content_types` says
    what qualifies.
    """
    support.member_of(g.library, support.memberships())
    report = render.sweep_content_types(g.library)
    return jsonify(report), 200


@bp.get("/renders/<render_id>")
def get_render(render_id: str):
    """One job: `queued`, `running`, `succeeded` with a `result`, or `failed` with an `error`.

    The `result` of a job that produced a file carries the node it created, so a
    caller that wants the bytes locally has everything it needs to sign a URL
    for them without a second lookup.
    """
    return jsonify(_job(render_id)), 200
