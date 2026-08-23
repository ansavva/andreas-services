"""Movies: scenes cut into one piece — the tier above a scene.

The thinnest of the five entity modules, and deliberately so. A movie is an
ordered list of scene ids, a folder, and one output; everything interesting about
what is in it lives on the scenes it names.

`PUT /api/movies/<id>/scenes` replaces the list rather than appending to it, for
`PUT /api/projects/<id>/characters`' reason: the client edits an ordered set and
an add-only endpoint would need a remove beside it, plus an ordering verb.

Stitching stays in the CLI. `ffmpeg` ships in the pipeline wheel and the Lambda
has none — the API owns the record, not the encode.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ValidationError
from studio_core.routes import projects as project_routes
from studio_core.routes import support
from studio_core.services import catalog, keys, layout

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
    slug = keys.clean_slug(body.get("slug"))
    scenes = body.get("scenes") or []
    if not isinstance(scenes, list):
        raise ValidationError("scenes must be a list")

    parent = project_routes.folder_for(project, layout.MOVIE_PARENT)
    record = catalog.create_project_entity(
        KIND,
        project["lib"],
        project["id"],
        parent["node_id"],
        slug=slug,
        attributes={
            "title": body.get("title") or slug,
            "status": "planned",
            "scenes": scenes,
            "output": None,
        },
        listing={"status": "planned", "title": body.get("title") or slug},
    )
    return jsonify(record), 201, {"Location": f"/api/movies/{record['id']}"}


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
    """The record, with the scenes it names resolved to slugs and status."""
    held = support.memberships()
    record = _movie(movie_id, held)

    found = catalog.entities_by_id(catalog.ENTITY_SCENE, record.get("scenes") or [])
    return jsonify(
        {
            **record,
            "scenes": [
                {
                    "id": scene_id,
                    "slug": found.get(scene_id, {}).get("slug"),
                    "status": found.get(scene_id, {}).get("status"),
                    "output": found.get(scene_id, {}).get("output"),
                }
                for scene_id in record.get("scenes") or []
            ],
        }
    ), 200


@bp.patch("/movies/<movie_id>")
def update_movie(movie_id: str):
    body = support.body()
    held = support.memberships()
    record = _movie(movie_id, held)

    assignments = {}
    listing = {}
    for field in ("title", "status"):
        if field in body:
            assignments[field] = body[field]
            listing[field] = body[field]
    if "output" in body:
        assignments["output"] = body["output"]
    if not assignments:
        raise ValidationError("nothing to change")
    return jsonify(catalog.update_project_entity(KIND, record, assignments, listing)), 200


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

    catalog.update_project_entity(KIND, record, {"scenes": scenes})
    return jsonify({"id": record["id"], "scenes": scenes}), 200


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
        KIND, record, {"output": node["node_id"]}, {"thumb": node["node_id"]}
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

    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    if result["blob_keys"]:
        s3.delete(result["blob_keys"])
    return jsonify({"id": record["id"], "files": files}), 200
