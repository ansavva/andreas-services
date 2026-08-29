"""Projects: a unit of production, and everything filed under one.

A project used to be a folder name. It is a row now — `PROJ#<proj_id>` / `META`
with a `LIB#<lib>` / `PROJSLUG#<slug>` claim — and it can therefore be renamed,
which was simply impossible before: the slug was the primary key, so a rename was
a tree rewrite and every run that had recorded a path was stranded by it.

**Characters involved are rows, not a list on the record.** `PROJ#<id>` /
`CHAR#<id>`, read forwards for "who is in this project" and backwards on `by-sk`
for "which projects involve this character". A list on the record would answer
the first and nothing at all for the second, and a character delete would have no
way to find what points at it.

**`counts` is maintained inside the transaction that moves it**, never scanned. A
project card shows runs, scenes and movies, and a screen that had to count them
would page every listing row to draw a tile.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.routes import support
from studio_core.services import catalog, keys, layout, manage

logger = logging.getLogger(__name__)

bp = Blueprint("projects", __name__, url_prefix="/api")

KIND = catalog.ENTITY_PROJECT


def project_at(addressed: str, held: dict) -> dict:
    """One project by id or `slug:<slug>`, membership-checked.

    Public because `routes/runs`, `routes/scenes` and `routes/movies` all resolve
    a project the same way and must not each grow their own version of it — three
    spellings of "which project is this, and may you touch it" is three places
    the membership check can be dropped.
    """
    return support.entity_at(KIND, g.library, addressed, held)


def _hero(record: dict, nodes: dict[str, dict]) -> dict | None:
    node = nodes.get(record.get("hero") or "")
    if not node or not node.get("blob_key"):
        return None
    return {"node": node["node_id"], "url": s3.presign(node["blob_key"])}


@bp.get("/projects")
def list_projects():
    """Every project in the library, with the counts already on the record."""
    held = support.memberships()
    support.member_of(g.library, held)

    listed = summary_rows(catalog.entities_in(g.library, KIND))
    return jsonify(listed), 200


def summary_rows(records: list[dict]) -> list[dict]:
    """A project as every listing spells it — slug-ascending.

    **One builder, because there was more than one listing.**
    `GET /api/characters/<id>/projects` answered the same conceptual thing —
    a project summary — with `{id, slug, title}` and nothing else, so the SPA
    drew it with the card it draws every other project list with and threw on
    `project.counts.runs`. Two routes returning "a project summary" in two
    shapes is the same defect as one relationship spelled two ways, one level
    up.

    `hero` costs the batched read it is worth: a listing without one is a grid
    of empty squares.
    """
    heroes = catalog.records([record["hero"] for record in records if record.get("hero")])
    rows = [
        {
            "id": record["id"],
            "slug": record["slug"],
            "title": record.get("title"),
            "hero": _hero(record, heroes),
            "counts": record.get("counts") or {},
            "updated": record.get("updated"),
        }
        for record in records
    ]
    rows.sort(key=lambda entry: entry["slug"])
    return rows


@bp.post("/projects")
def create_project():
    """A project, its claim, its root, its five subfolders and its involvements."""
    body = support.body()
    held = support.memberships()
    support.member_of(g.library, held)

    slug = keys.clean_slug(body.get("slug"))
    characters = body.get("characters") or []
    if not isinstance(characters, list):
        raise ValidationError("characters must be a list")
    for char_id in characters:
        # Read to prove it exists and is in this library. A link to a character
        # that is not there would answer "which projects involve it" forever.
        support.entity_at(catalog.ENTITY_CHARACTER, g.library, char_id, held)

    root = catalog.library(g.library)["root_node"]
    try:
        record = catalog.create_project(
            g.library,
            root,
            slug=slug,
            title=body.get("title"),
            description=body.get("description"),
            characters=characters,
            layout=layout.PROJECT_LAYOUT,
        )
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)

    return jsonify({**record, "characters": _characters(record)}), 201, {
        "Location": f"/api/projects/{record['id']}"
    }


@bp.get("/projects/<addressed>")
def get_project(addressed: str):
    """The record, with the characters it involves resolved to slugs."""
    held = support.memberships()
    record = project_at(addressed, held)
    return jsonify({**record, "characters": _characters(record)}), 200


def _characters(record: dict) -> list[dict]:
    ids = catalog.links(record["id"], catalog.ENTITY_CHARACTER)
    found = catalog.entities_by_id(catalog.ENTITY_CHARACTER, ids)
    return [
        {
            "id": character["id"],
            "slug": character["slug"],
            "display_name": character.get("display_name"),
        }
        for character in found.values()
    ]


@bp.patch("/projects/<addressed>")
def update_project(addressed: str):
    """Rename, retitle, re-hero — under a `rev`. **Zero objects are copied.**"""
    body = support.body()
    held = support.memberships()
    record = project_at(addressed, held)
    rev = support.revision(body, record)

    assignments = {}
    for field in ("title", "description"):
        if field in body:
            if not isinstance(body[field], str):
                raise ValidationError(f"{field} must be a string")
            assignments[field] = body[field]
    if "hero" in body:
        if body["hero"]:
            node = catalog.node(body["hero"])
            if node["lib"] != record["lib"]:
                raise ValidationError("hero names a node in another library")
            assignments["hero"] = node["node_id"]
        else:
            assignments["hero"] = None

    slug = keys.clean_slug(body["slug"]) if body.get("slug") else None
    try:
        updated = catalog.update_entity(KIND, record, rev, assignments, slug=slug)
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)
    return jsonify(updated), 200


@bp.delete("/projects/<addressed>")
def delete_project(addressed: str):
    """Remove a project. `?files=keep|delete`; refuses while it holds runs.

    The refusal is about the rows rather than the folder: a run's envelope names
    its project, and deleting the project leaves every one of them pointing at
    nothing.

    **`?cascade=1` is the answer to that, and `?force=1` never was.** Cascade
    deletes the movies, then the scenes, then the runs, then the project — see
    `delete_project_cascade` for why the order is the safety and why it cannot
    be one transaction. Force still means "delete the project and leave its
    children naming a project that is gone", which is a broken catalog and is
    kept only because something may already depend on it; prefer cascade.
    """
    held = support.memberships()
    record = project_at(addressed, held)

    files = request.args.get("files") or "keep"
    if files not in ("keep", "delete"):
        raise ValidationError("files must be 'keep' or 'delete'")

    cascade = request.args.get("cascade") in ("1", "true")
    counts = record.get("counts") or {}
    held_entities = sum(int(counts.get(field) or 0) for field in ("runs", "scenes", "movies"))
    # **Drafts are held by the project and are not in its counts**, so the guard
    # has to ask for them separately or a project holding nothing but unsubmitted
    # work would delete without a word. A run is counted when it is submitted —
    # that is what keeps a project's run count meaning "runs made" — and this is
    # the one place where the distinction would have cost data rather than
    # tidiness. One query, on a path that runs once per project deletion.
    drafts = sum(
        1
        for row in catalog.project_entities(record["id"], catalog.ENTITY_RUN)
        if row.get("status") in catalog.HIDDEN_RUN_STATUSES
    )
    held_entities += drafts
    if held_entities and not cascade and request.args.get("force") not in ("1", "true"):
        return support.structured(
            "conflict",
            f"this project holds {held_entities} run(s), scene(s) and movie(s) — "
            "pass ?cascade=1 to delete them with it",
            409,
            # Both numbers, because they answer different questions and a client
            # showing one as the other would be wrong. `counts` is what the
            # project has MADE; `drafts` is unsubmitted work that would be
            # deleted alongside it and that no count mentions.
            counts={**counts, "drafts": drafts},
        )

    manage.drain(g.library)
    if cascade:
        result = catalog.delete_project_cascade(record, delete_files=files == "delete")
    else:
        result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    manage.release(g.library, result["blob_keys"], result["sweeps"])
    return jsonify({"id": record["id"], "files": files,
                    "removed": result.get("removed") or {}}), 200


@bp.patch("/projects/<addressed>/characters")
def set_characters(addressed: str):
    """Replace the involvement links.

    A replace rather than an add, because the SPA edits a set and `projects link`
    reads the set first — an add-only endpoint would need a remove beside it, and
    a client that got the difference wrong would accumulate links nothing removes.

    **The answer is the same shape `GET` sends**, and used to be the bare ids
    this was handed. A record holds `characters` as expanded objects, so a
    client merging this response into the record it already had replaced those
    objects with strings — the write succeeded and every chip downstream read
    unselected, with no type able to catch it. Returning what `GET` returns is
    what makes the response mergeable at all.
    """
    body = support.body()
    held = support.memberships()
    record = project_at(addressed, held)

    characters = body.get("characters")
    if not isinstance(characters, list):
        raise ValidationError("characters must be a list")
    for char_id in characters:
        support.entity_at(catalog.ENTITY_CHARACTER, g.library, char_id, held)

    catalog.set_project_characters(record["id"], record["lib"], characters)
    return jsonify({"id": record["id"], "characters": _characters(record)}), 200


@bp.get("/projects/<addressed>/inputs")
def inputs(addressed: str):
    """The working pool, name-ascending. **Position in this list is `--input N`.**

    Numbered in the response rather than left to the caller, because the position
    *is* the address: two clients sorting a listing differently would disagree
    about what `--input 3` means, and that disagreement would only ever be visible
    in the output of a generation.

    The folder is resolved by name and made if it is absent, which is
    `services.layout`'s rule: a project whose `input/` somebody deleted gets a new
    one rather than a 404.
    """
    held = support.memberships()
    record = project_at(addressed, held)

    folder = layout.folder_under(record["root"], layout.INPUT_FOLDER)
    entries = catalog.children(folder["node_id"])
    full = catalog.records([entry["node_id"] for entry in entries])

    files = [
        full[entry["node_id"]]
        for entry in entries
        if full.get(entry["node_id"], {}).get("kind") == catalog.KIND_FILE
    ]
    files.sort(key=lambda node: node["name"])
    return jsonify(
        {
            "folder": folder["node_id"],
            "inputs": [
                {
                    "position": position,
                    "id": node["node_id"],
                    "name": node["name"],
                    "size": node.get("size"),
                    "content_type": node.get("content_type"),
                    "url": s3.presign(node["blob_key"]) if node.get("blob_key") else None,
                }
                for position, node in enumerate(files, start=1)
            ],
        }
    ), 200


@bp.get("/projects/<addressed>/runs")
def project_runs(addressed: str):
    """A project's runs, newest first, from the listing rows.

    Rows rather than envelopes, deliberately: this is what draws the grid, and
    fetching the envelopes would be the `BatchGetItem` the projection exists to
    avoid. Filters run in memory over one query's worth of rows — a project holds
    hundreds of runs, and a filtered index per field would be four GSIs for a
    screen.
    """
    held = support.memberships()
    record = project_at(addressed, held)
    return jsonify(_listing(record, catalog.ENTITY_RUN, request.args)), 200


@bp.get("/projects/<addressed>/scenes")
def project_scenes(addressed: str):
    held = support.memberships()
    record = project_at(addressed, held)
    return jsonify(_listing(record, catalog.ENTITY_SCENE, request.args)), 200


@bp.get("/projects/<addressed>/movies")
def project_movies(addressed: str):
    held = support.memberships()
    record = project_at(addressed, held)
    return jsonify(_listing(record, catalog.ENTITY_MOVIE, request.args)), 200


def _listing(record: dict, kind: str, args) -> dict:
    rows = catalog.project_entities(record["id"], kind)
    for field in ("status", "model", "kind"):
        wanted = args.get(field)
        if wanted:
            rows = [row for row in rows if row.get(field) == wanted]
    since = args.get("since")
    if since:
        rows = [row for row in rows if (row.get("created") or "") >= since]

    thumbs = catalog.records([row["thumb"] for row in rows if row.get("thumb")])
    for row in rows:
        node = thumbs.get(row.get("thumb") or "")
        if node and node.get("blob_key"):
            row["thumb"] = {"node": node["node_id"], "url": s3.presign(node["blob_key"])}
        elif "thumb" in row:
            row["thumb"] = None
    return {kind + "s": rows, "cursor": None}


def folder_for(record: dict, name: str) -> dict:
    """The conventional folder a project-scoped entity is created under.

    Here rather than in each of the three route modules so that "where does a run
    go" has one answer. A missing `root` is a project written by hand and is the
    one case this cannot self-heal from.
    """
    root = record.get("root")
    if not root:
        raise NotFoundError(record["id"])
    return layout.folder_under(root, name)
