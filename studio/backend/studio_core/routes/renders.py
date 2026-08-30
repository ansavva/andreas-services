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


@bp.get("/renders/<render_id>")
def get_render(render_id: str):
    """One job: `queued`, `running`, `succeeded` with a `result`, or `failed` with an `error`.

    The `result` of a job that produced a file carries the node it created, so a
    caller that wants the bytes locally has everything it needs to sign a URL
    for them without a second lookup.
    """
    return jsonify(_job(render_id)), 200
