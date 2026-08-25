"""Scenes: shots stitched into one continuous take.

The tier above a run, and the same envelope-plus-blob split — with one addition
that is the whole reason a scene is not just a folder of runs: **the plan**.
`SCENE#<id>` / `SHOT#<shot_id>` is one row per planned shot, carrying `order`,
`prompt`, and the `run` and `panel` that rendered it.

**A plan revision merges onto rendered work rather than replacing it.** That is
the one non-obvious rule in this module and it is `catalog.put_shots`'. Rewriting
prompts is what a person does to a plan; `run` and `panel` are what a render put
there, and a plain replace would silently discard them — so a shot matched by id
keeps both unless the request names them.

**Stitching stays in the CLI.** `ffmpeg` ships in the pipeline wheel and the
Lambda has none, so `assemble` downloads, stitches locally, uploads through
`POST /api/scenes/<id>/output` and `PATCH`es the record. The API owns the record,
not the encode.

**No `rev` on the writes here, and that is a rule rather than an omission.** A
character and a project are edited by people, twice at once, and losing somebody's
paragraph is what optimistic concurrency exists to prevent. A run, a scene and a
movie are driven by the machine that is rendering them, in sequence — demanding a
`rev` would make the CLI re-read a record to report that a shot finished.
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

bp = Blueprint("scenes", __name__, url_prefix="/api")

KIND = catalog.ENTITY_SCENE


def _scene(scene_id: str, held: dict) -> dict:
    return support.entity_at(KIND, g.library, scene_id, held)


def _shots(raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("shots must be a list")
    for shot in raw:
        if not isinstance(shot, dict):
            raise ValidationError("every shot must be an object")
    return raw


@bp.post("/scenes")
def create_scene():
    """A scene, its listing row, its folder and its plan — one write plus the shots."""
    body = support.body()
    held = support.memberships()

    project = project_routes.project_at(body.get("project") or "", held)
    slug = keys.clean_slug(body.get("slug"))
    shots = _shots(body.get("shots"))

    parent = project_routes.folder_for(project, layout.SCENE_PARENT)
    record = catalog.create_project_entity(
        KIND,
        project["lib"],
        project["id"],
        parent["node_id"],
        slug=slug,
        attributes={
            "title": body.get("title") or slug,
            "status": "planned",
            "output": None,
            "error": None,
        },
        listing={"status": "planned", "title": body.get("title") or slug},
    )

    written = catalog.put_shots(record["id"], shots) if shots else []
    return jsonify({**record, "shots": written}), 201, {
        "Location": f"/api/scenes/{record['id']}"
    }


@bp.get("/scenes")
def list_scenes():
    """Every scene in a project, or in the library when no project is named."""
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
    return jsonify({"scenes": rows, "cursor": None}), 200


@bp.get("/scenes/<scene_id>")
def get_scene(scene_id: str):
    """The record and its shots, in `order`."""
    held = support.memberships()
    record = _scene(scene_id, held)
    return jsonify({**support.with_output(record),
                    "shots": catalog.shots(record["id"])}), 200


# What a PATCH may write, and it is the list of what actually writes to a scene.
#
# It held three names — `title`, `status`, `error` — and `assemble` sends four
# others: `characters`, `stitch`, `output` and `assembled`. None of them matched,
# so the request reached `nothing to change` and 400ed *after* the stitched video
# had been encoded locally and uploaded. The cut was in the bucket and the scene
# never learned it had one.
#
# `stitch` and `output` are the encoder's own report and are stored without being
# read: `ffmpeg` ships in the CLI's wheel and the Lambda has none, so how the
# file was made is not this service's to validate. `movies.py` accepted `output`
# already, which is why a movie assembled and a scene did not.
SCENE_FIELDS = ("title", "status", "error", "characters", "stitch", "output", "assembled")

# The projection the listing row carries, and the only fields worth a second
# write. A grid draws a scene from these.
SCENE_LISTED = ("title", "status")


@bp.patch("/scenes/<scene_id>")
def update_scene(scene_id: str):
    """Retitle a scene, move its status on, or record the cut `assemble` made."""
    body = support.body()
    held = support.memberships()
    record = _scene(scene_id, held)

    assignments = {}
    listing = {}
    for field in SCENE_FIELDS:
        if field in body:
            assignments[field] = body[field]
            if field in SCENE_LISTED:
                listing[field] = body[field]
    if "output" in body:
        # The cut is what a scene looks like, so recording one re-points the
        # thumbnail — the same thing `POST /scenes/<id>/output` does, and it has
        # to happen here too because `assemble` may write a different node than
        # the one it signed for.
        node = support.output_node(body["output"])
        if node:
            listing["thumb"] = node
    if not assignments:
        raise ValidationError("nothing to change")
    return jsonify(
        support.with_output(catalog.update_project_entity(KIND, record, assignments, listing))
    ), 200


@bp.patch("/scenes/<scene_id>/shots")
def replace_shots(scene_id: str):
    """The plan revision — **merged onto rendered work, not over it**."""
    body = support.body()
    held = support.memberships()
    record = _scene(scene_id, held)
    return jsonify({"shots": catalog.put_shots(record["id"], _shots(body.get("shots")))}), 200


@bp.patch("/scenes/<scene_id>/shots/<shot_id>")
def update_shot(scene_id: str, shot_id: str):
    """One shot: which run rendered it, which panel it came from, its wording."""
    body = support.body()
    held = support.memberships()
    record = _scene(scene_id, held)

    changes = {field: body[field] for field in ("run", "panel", "prompt", "order")
               if field in body}
    if not changes:
        raise ValidationError("nothing to change")
    return jsonify(catalog.update_shot(record["id"], shot_id, changes)), 200


@bp.post("/scenes/<scene_id>/output")
def add_output(scene_id: str):
    """A placeholder and a presigned PUT for the stitched take.

    One output rather than a list, because a scene *is* one take — the shots that
    made it are `SHOT#` rows naming their own runs, and each of those has its own
    outputs.
    """
    body = support.body()
    held = support.memberships()
    record = _scene(scene_id, held)

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


@bp.delete("/scenes/<scene_id>")
def delete_scene(scene_id: str):
    """Remove a scene and its shots. `?files=keep|delete`, keeping by default."""
    held = support.memberships()
    record = _scene(scene_id, held)

    files = request.args.get("files") or "keep"
    if files not in ("keep", "delete"):
        raise ValidationError("files must be 'keep' or 'delete'")

    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    if result["blob_keys"]:
        s3.delete(result["blob_keys"])
    return jsonify({"id": record["id"], "files": files}), 200
