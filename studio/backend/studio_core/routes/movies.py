"""Movies: scenes cut into one piece — the tier above a scene.

The thinnest of the five entity modules, and deliberately so. A movie is an
ordered list of scene ids, a folder, and one output; everything interesting about
what is in it lives on the scenes it names.

`PUT /api/movies/<id>/scenes` replaces the list rather than appending to it, for
`PUT /api/projects/<id>/characters`' reason: the client edits an ordered set and
an add-only endpoint would need a remove beside it, plus an ordering verb.

Stitching is a render job. It used to stay in the CLI, because `ffmpeg` shipped
in the pipeline wheel and the Lambda had none; a second container image has it
now, and `services/render.py` enqueues the cut. This module still owns the
record, and now shares it: the worker writes `output`, `stitch`, `cuts` and
`assembled` when a cut lands.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ValidationError
from studio_core.routes import projects as project_routes
from studio_core.routes import support
from studio_core.services import catalog, keys, layout, manage

logger = logging.getLogger(__name__)

bp = Blueprint("movies", __name__, url_prefix="/api")

KIND = catalog.ENTITY_MOVIE


def _movie(movie_id: str, held: dict) -> dict:
    return support.entity_at(KIND, g.library, movie_id, held)


@bp.post("/movies")
def create_movie():
    """A movie, its listing row and its folder — one write."""
    body = support.body()
    held = support.memberships()

    project = project_routes.project_at(body.get("project") or "", held)
    name = keys.clean_label(body.get("name"))
    scenes = body.get("scenes") or []
    if not isinstance(scenes, list):
        raise ValidationError("scenes must be a list")

    parent = project_routes.folder_for(project, layout.MOVIE_PARENT)
    record = catalog.create_project_entity(
        KIND,
        project["lib"],
        project["id"],
        parent["node_id"],
        attributes={
            "name": name,
            "status": "planned",
            "scenes": scenes,
            "output": None,
        },
        # `name` is in the projection because a row without one cannot be
        # DRAWN, and a list of UUIDs is a list nobody can read. It used to carry
        # `slug` as well, for addressing; the only address is the id now.
        listing={"status": "planned", "name": name},
    )
    # Expanded, because `GET` expands. A create that answered with the raw id
    # list made this the fourth endpoint in the service to spell one
    # relationship two ways depending on which verb you used.
    return jsonify({**record, "scenes": _scene_rows(record)}), 201, {
        "Location": f"/api/movies/{record['id']}"
    }


@bp.get("/movies")
def list_movies():
    held = support.memberships()
    support.member_of(g.library, held)

    if request.args.get("project"):
        project = project_routes.project_at(request.args["project"], held)
        rows = catalog.project_entities(project["id"], KIND)
    else:
        rows = []
        for project in catalog.entities_in(g.library, catalog.ENTITY_PROJECT):
            rows.extend(catalog.project_entities(project["id"], KIND))
        rows.sort(key=lambda row: row.get("created") or "", reverse=True)
    return jsonify({"movies": rows, "cursor": None}), 200


@bp.get("/movies/<movie_id>")
def get_movie(movie_id: str):
    """The record, with the scenes it names resolved to names and status."""
    held = support.memberships()
    record = _movie(movie_id, held)

    return jsonify({**support.with_output(record), "scenes": _scene_rows(record)}), 200


def _scene_rows(record: dict) -> list[dict]:
    """The scenes a movie cuts, in order, as **every** response spells them.

    One builder, because `GET` and the scenes write used to spell this
    differently: `GET` sent rows and the write answered with the bare ids it had
    been given. A client that merged the write's answer into the record it was
    holding replaced rows with strings and every consumer downstream read empty.
    That is not hypothetical — it is the bug this shape already caused on
    `PUT /projects/<id>/characters`, and this endpoint was one caller away from
    the same thing.

    Order and duplicates come from the list, which is what a movie contributes:
    the same scene may legally be cut twice as a reprise.
    """
    ordered = record.get("scenes") or []
    found = catalog.entities_by_id(catalog.ENTITY_SCENE, ordered)

    # One batched read for every cut in the list, rather than one per row. A
    # movie names as many scenes as it names.
    cuts = [support.output_node((found.get(scene_id) or {}).get("output"))
            for scene_id in ordered]
    nodes = catalog.records([node for node in cuts if node])

    return [
        _scene_row(scene_id, found.get(scene_id) or {}, node, nodes)
        for scene_id, node in zip(ordered, cuts)
    ]


def _scene_row(scene_id: str, scene: dict, node: str | None, nodes: dict) -> dict:
    """A scene as a movie lists it — enough to draw a row, not the whole record.

    **`title` and `thumb` are here because a row without them cannot be drawn.**
    They were not, so the SPA's cut list showed every scene by its id behind an
    empty square. A scene's thumbnail is its own cut, which is why `thumb` is
    derived from `output` rather than read off a listing row: the listing row is
    the project's, and this query goes to the scene records.
    """
    drawable = support.asset(node, nodes.get(node)) if node else None
    return {
        "id": scene_id,
                "name": scene.get("name"),
        "status": scene.get("status"),
        "output": drawable,
        "thumb": drawable,
    }


# What a PATCH may write. `characters`, `stitch` and `assembled` are what
# `assemble` sends and what this route silently dropped — `output` was accepted,
# so a movie recorded its cut while losing the report of how it was made.
MOVIE_FIELDS = ("name", "status", "output", "characters", "stitch", "assembled")

# The projection the listing row carries. A grid draws a movie from these.
MOVIE_LISTED = ("name", "status")


@bp.patch("/movies/<movie_id>")
def update_movie(movie_id: str):
    body = support.body()
    held = support.memberships()
    record = _movie(movie_id, held)

    assignments = {}
    listing = {}
    for field in MOVIE_FIELDS:
        if field in body:
            assignments[field] = body[field]
            if field in MOVIE_LISTED:
                listing[field] = body[field]
    if "output" in body:
        # Recording the cut re-points the thumbnail, as `POST .../output` does.
        node = support.output_node(body["output"])
        if node:
            listing["thumb"] = node
    if not assignments:
        raise ValidationError("nothing to change")
    return jsonify(
        support.with_output(catalog.update_project_entity(KIND, record, assignments, listing))
    ), 200


@bp.patch("/movies/<movie_id>/scenes")
def set_scenes(movie_id: str):
    """The cut, as an ordered list of scene ids.

    Each one is read before it is written, so a movie cannot name a scene that is
    not there — the list is what `assemble` walks, and a missing id there is a
    stitch that fails half way through an upload rather than at the request that
    caused it.
    """
    body = support.body()
    held = support.memberships()
    record = _movie(movie_id, held)

    scenes = body.get("scenes")
    if not isinstance(scenes, list):
        raise ValidationError("scenes must be a list")
    for scene_id in scenes:
        support.entity_at(catalog.ENTITY_SCENE, g.library, scene_id, held)

    catalog.update_project_entity(KIND, record, {"scenes": scenes},
                                  edges={catalog.ENTITY_SCENE: scenes})
    return jsonify({"id": record["id"],
                    "scenes": _scene_rows({**record, "scenes": scenes})}), 200


@bp.post("/movies/<movie_id>/output")
def add_output(movie_id: str):
    """A placeholder and a presigned PUT for the finished cut."""
    body = support.body()
    held = support.memberships()
    record = _movie(movie_id, held)

    size = body.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValidationError("size must be a non-negative integer")
    if size > config.max_upload_bytes():
        raise ValidationError(f"an output must be at most {config.max_upload_bytes()} bytes")
    content_type = body.get("content_type")
    if not isinstance(content_type, str) or not content_type:
        raise ValidationError("content_type is required")

    node = catalog.create_node(
        record["folder"],
        body.get("name"),
        catalog.KIND_FILE,
        owner=catalog.blob_owner_for(record["folder"]),
    )
    catalog.update_project_entity(
        KIND, record, {"output": {"node": node["node_id"]}}, {"thumb": node["node_id"]}
    )

    return jsonify(
        {
            "node": node["node_id"],
            "url": s3.presign_put(
                node["blob_key"], content_length=size, content_type=content_type
            ),
            "expires_in": config.upload_ttl_seconds(),
            "headers": {"Content-Length": str(size), "Content-Type": content_type},
        }
    ), 201


@bp.delete("/movies/<movie_id>")
def delete_movie(movie_id: str):
    held = support.memberships()
    record = _movie(movie_id, held)

    files = request.args.get("files") or "keep"
    if files not in ("keep", "delete"):
        raise ValidationError("files must be 'keep' or 'delete'")

    manage.drain(g.library)
    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    manage.release(g.library, result["blob_keys"], result["sweeps"])
    return jsonify({"id": record["id"], "files": files}), 200
