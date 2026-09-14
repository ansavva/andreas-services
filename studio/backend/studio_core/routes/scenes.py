"""Scenes: a named, ordered series of runs — the tier above a run.

**A scene is not a data model of its own.** It was: `SCENE#<id>` carried a plan
— a `setting`, `defaults`, one `SHOT#` row per planned shot, each with its
panels, its motion prompt, the run that rendered it and the frame it opened on —
and 700 lines of storyboard service normalised, validated, merged and derived
status over it. Every one of those things was already a run: a panel is an
image run, a shot is a video run, "which frame it opens on" is that run's
`start` send, and "which run rendered it" was the shot pointing at the thing
that was already the record. The plan was a second description of the same
runs, kept in step by hand.

So a scene is now two facts and a name:

| Fact | Where | Edge beside it |
|---|---|---|
| a run belongs to a scene | `scene` on the run (`routes/runs.py`) | `RUN#<run>` / `SCENE#<scene>` |
| the cut, in order | `runs` on the scene | `SCENE#<scene>` / `RUN#<run>` |

Membership takes stills and clips alike — every run made FOR the scene, which
is what a person looking at the scene wants to see together. The cut names the
video runs in the order they are stitched, and may name a run that has not
rendered yet: the cut is the plan. `assemble` refuses until every run in it has
a clip.

**Stitching is a render job.** `services/render.py` enqueues a cut and a worker
Lambda with ffmpeg in its image does the download, the stitch and the record.
`POST /api/scenes/<id>/output` signs an upload for a cut made somewhere else,
which is what a client holding the bytes wants; the render path does not use it.

**No `rev` on the writes here, and that is a rule rather than an omission.** A
character and a project are edited by people, twice at once, and losing
somebody's paragraph is what optimistic concurrency exists to prevent. A scene
is driven by the machine that is rendering it, in sequence.
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

bp = Blueprint("scenes", __name__, url_prefix="/api")

KIND = catalog.ENTITY_SCENE

#: What a run row in the cut carries — the listing fields every run list draws,
#: plus the clip. The SPA's `SceneCut` type mirrors it.
RUN_ROW = ("id", "project", "status", "kind", "model", "created")


def _scene(scene_id: str, held: dict) -> dict:
    return support.entity_at(KIND, g.library, scene_id, held)


def _cut_of(body: dict, record: dict, held: dict) -> list[str]:
    """Validate the cut a request names, and put each run into the scene.

    **Naming a run in the cut is what puts it in the scene.** A run with no
    scene gets this one; a run already in this scene is left alone; a run in
    another scene is refused, because a run belongs to at most one and moving
    it is a decision to make on the run, not a side effect of ordering a cut.

    Every entry is read before anything is written, so a cut cannot name a run
    that is not there, is not this project's, or is a still — the cut is what
    `assemble` walks, and a still there is a stitch that fails at the far end
    of a queue rather than at the request that caused it. Duplicates are legal:
    a clip may be reprised, and the edge rows beside the list deduplicate.
    """
    runs = body.get("runs")
    if runs is None:
        return []
    if not isinstance(runs, list) or not all(isinstance(r, str) for r in runs):
        raise ValidationError("runs must be a list of run ids")
    for run_id in dict.fromkeys(runs):
        run = support.entity_at(catalog.ENTITY_RUN, g.library, run_id, held)
        if run.get("project") != record["project"]:
            raise ValidationError(f"{run_id} is not in this project")
        if run.get("kind") != "video":
            raise ValidationError(f"{run_id} is a {run.get('kind')} run; only a video can be cut")
        if run.get("scene") and run["scene"] != record["id"]:
            raise ValidationError(f"{run_id} belongs to scene {run['scene']}")
    return runs


def _join(record: dict, runs: list[str]) -> None:
    """Put every run the cut names into the scene, if it is not already."""
    for run_id in dict.fromkeys(runs):
        run = catalog.entity(catalog.ENTITY_RUN, run_id)
        if run.get("scene") == record["id"]:
            continue
        catalog.update_project_entity(
            catalog.ENTITY_RUN, run, {"scene": record["id"]}, {"scene": record["id"]},
            edges={KIND: [record["id"]]})


def _cut_rows(record: dict) -> list[dict]:
    """The runs a scene cuts, in order, as **every** response spells them.

    One builder, for the reason `routes/movies._scene_rows` gives: `GET` and
    the write that changes the list answering in different shapes is how a
    client that merges a write's answer ends up holding strings where it read
    rows. Each row is the listing fields plus the run's first video output,
    signed, so the page can draw the cut without a fetch per run — and a run
    that has not rendered yet draws as a row with no clip, which is what a
    planned cut looks like.
    """
    ordered = record.get("runs") or []
    found = catalog.entities_by_id(catalog.ENTITY_RUN, ordered)
    firsts = {run_id: ((found.get(run_id) or {}).get("outputs") or [None])[0]
              for run_id in ordered}
    nodes = catalog.records([node for node in firsts.values() if node])
    rows = []
    for run_id in ordered:
        run = found.get(run_id) or {}
        node = firsts.get(run_id)
        clip = support.asset(node, nodes.get(node)) if node else None
        rows.append({**{field: run.get(field) for field in RUN_ROW}, "id": run_id,
                     "scene": run.get("scene"), "output": clip, "thumb": clip})
    return rows


def _frames(record: dict) -> list[dict]:
    """The scene's own frames: the first frame each run in the cut opened on.

    A chained scene is built from these — the seed shot 1 started from, then
    each later shot's handoff — and they are what shot N+1 should be handed as
    references, not the character's curated set (`studio-media-scene` says
    why). Derived from the cut's `start` sends on read rather than kept: the
    `chains/<scene>.json` and `scene_frames` that used to hold this list both
    drifted from the scene they described.
    """
    ordered = list(dict.fromkeys(record.get("runs") or []))
    starts = []
    for run_id in ordered:
        for entry in catalog.sends(run_id):
            if entry.get("role") == "start" and entry.get("node") not in starts:
                starts.append(entry["node"])
                break
    return support.assets(starts)


def _view(record: dict) -> dict:
    """The record, its cut expanded, its frames and the way back up."""
    return {**support.with_output(record),
            "runs": _cut_rows(record),
            "frames": _frames(record),
            "movies": support.holders(record["id"], catalog.ENTITY_MOVIE)}


@bp.post("/scenes")
def create_scene():
    """A scene, its listing row, its folder and — if named — its cut. One write."""
    body = support.body()
    held = support.memberships()

    project = project_routes.project_at(body.get("project") or "", held)
    name = keys.clean_label(body.get("name"))
    runs = _cut_of(body, {"id": None, "project": project["id"]}, held)

    parent = project_routes.folder_for(project, layout.SCENE_PARENT)
    record = catalog.create_project_entity(
        KIND,
        project["lib"],
        project["id"],
        parent["node_id"],
        attributes={"name": name, "status": "planned", "runs": runs,
                    "output": None, "error": None},
        # `name` belongs in the projection because a row without one cannot be
        # DRAWN. The only address is the id.
        listing={"status": "planned", "name": name},
    )
    _join(record, runs)
    return jsonify(_view(record)), 201, {"Location": f"/api/scenes/{record['id']}"}


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
    """The record, its cut, its frames, and which movies cut it.

    The runs that belong to the scene are not here: they are a run listing,
    `GET /api/runs?scene=<id>`, paginated and filterable like any other, so the
    same feed that draws a project draws a scene.
    """
    held = support.memberships()
    return jsonify(_view(_scene(scene_id, held))), 200


# What a PATCH may write, and it is the list of what actually writes to a scene.
# `stitch`, `output`, `assembled` and `cuts` are the encoder's report: the
# render worker writes them through `update_project_entity` itself, and this
# route accepts them from a client that made a cut some other way.
SCENE_FIELDS = ("name", "status", "error", "characters", "stitch", "output",
                "assembled", "cuts")

# The projection the listing row carries. A grid draws a scene from these.
SCENE_LISTED = ("name", "status")


@bp.patch("/scenes/<scene_id>")
def update_scene(scene_id: str):
    """Rename a scene, move its status on, or record a cut made elsewhere."""
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
        # thumbnail, and the cut it displaces is kept — read off the stored
        # record, not the incoming value.
        node = support.output_node(body["output"])
        assignments["cuts"] = support.keep_cut(record, node)
        if node:
            listing["thumb"] = node
    if not assignments:
        raise ValidationError("nothing to change")
    return jsonify(
        _view(catalog.update_project_entity(KIND, record, assignments, listing))
    ), 200


@bp.patch("/scenes/<scene_id>/runs")
def set_runs(scene_id: str):
    """The cut, as an ordered list of run ids. A replace, like every list here.

    The list and its edge rows land in one transaction, so "which scenes cut
    this run" and the order it is cut in cannot disagree. Each run named joins
    the scene first — see `_cut_of`.
    """
    body = support.body()
    held = support.memberships()
    record = _scene(scene_id, held)

    if not isinstance(body.get("runs"), list):
        raise ValidationError("runs must be a list")
    runs = _cut_of(body, record, held)
    _join(record, runs)
    updated = catalog.update_project_entity(
        KIND, record, {"runs": runs}, edges={catalog.ENTITY_RUN: runs})
    return jsonify({"id": record["id"], "runs": _cut_rows(updated)}), 200


@bp.post("/scenes/<scene_id>/output")
def add_output(scene_id: str):
    """A placeholder and a presigned PUT for a cut stitched somewhere else.

    One CURRENT output rather than a list, because a scene *is* one take — the
    runs that made it each have their own outputs. The take it displaces moves
    to `cuts`, because assembling is not a one-shot act.
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
        KIND, record,
        {"output": {"node": node["node_id"]},
         "cuts": support.keep_cut(record, node["node_id"])},
        {"thumb": node["node_id"]},
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
    """Remove a scene. `?files=keep|delete`, keeping by default.

    **Its runs stay, and stop naming it.** A run is the record and the scene
    was only ever a grouping of them, so deleting the grouping leaves every run
    where it is — `scene` cleared, so nothing points at an id that is gone.
    The edge rows go with the scene's partition and the holders' rows in
    `delete_entity`; the attribute is cleared here because it is a field on
    another record, which is the one thing a partition delete cannot reach.
    """
    held = support.memberships()
    record = _scene(scene_id, held)

    files = request.args.get("files") or "keep"
    if files not in ("keep", "delete"):
        raise ValidationError("files must be 'keep' or 'delete'")

    for run in catalog.runs_in_scene(record["id"]):
        catalog.update_project_entity(
            catalog.ENTITY_RUN, run, {"scene": None}, {"scene": None})
    manage.drain(g.library)
    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    manage.release(g.library, result["blob_keys"], result["sweeps"])
    return jsonify({"id": record["id"], "files": files}), 200
