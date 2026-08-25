"""Runs: one submission to a model, as an envelope studio owns and a blob it does not.

A run used to be a folder named `<ts>_<slug>` holding three JSON documents nobody
was allowed to parse. The consequence was that the app could show a run as a
folder and nothing else, and that `runs find --character` meant listing every
project, listing every run in each, reading `request.json` for each, and
grepping.

**The split that makes a run presentable without making this service a liar:**

| Studio owns (row, validated, queryable) | The provider owns (blob, verbatim) |
|---|---|
| id, project, status, kind, engine, model, prediction id, timings, bindings, characters, folder, outputs, lineage, cost, error | the exact `input` sent, the exact response returned |

The old rule — "do not decode `request.json`" — is not weakened; it is moved to
where it is actually true. The pipeline changes the payload's shape freely, so
anything here that read a key inside one would become wrong without notice. What
this module *does* do is re-encode the `input` object it was handed into the
bytes it stores, which is not the same as reading it.

## Hard rule #3 now lives here

**S3 is the only origin.** Assets are never uploaded to a model provider;
anything sent to a model must already be an S3 object and reaches Replicate as a
short-lived presigned URL. That was enforced in `runs.py` in the pipeline — which
only the CLI goes through. It is enforced here now, which is a strengthening
rather than a move: the API is the only thing *both* halves of studio pass
through, so a URL where a node id belongs is refused for the SPA too.

The refusal is a **400 carrying a code**, because a client has to act on it —
upload the bytes first — and matching on prose is how that stops working.
"""

import json
import logging
import re

from flask import Blueprint, g, jsonify, request

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ValidationError
from studio_core.routes import projects as project_routes
from studio_core.routes import support
from studio_core.services import catalog, layout

logger = logging.getLogger(__name__)

bp = Blueprint("runs", __name__, url_prefix="/api")

KIND = catalog.ENTITY_RUN

# What a run produces. Not the model's `kind` field and not a content type — this
# is the two shapes the pipeline distinguishes everywhere else.
RUN_KINDS = frozenset({"image", "video"})

# What a URL-shaped binding looks like: **anything carrying a URI scheme.**
#
# Deliberately wider than `^https?://`, and the width is the point. What is being
# prevented is a provider-hosted asset reaching a model, and the shapes that do
# that are not all `https`: `s3://bucket/key` is somebody else's bucket,
# `data:image/png;base64,…` is bytes inlined past every check this service makes,
# and `file:///…` is a path on whatever machine composed the request. A narrow
# check would pass three of the four, and none of them is a node id either.
#
# A node id is `node-<uuid4>` and holds no colon, so this cannot false-positive
# on one.
URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def validate_bindings(raw, lib: str) -> dict:
    """Bindings as node ids, or the refusal hard rule #3 exists to make.

    **Every value is a list of node ids that exist in this library**, and all
    three of those are checked. A URI scheme is the rule; a node that does not
    exist is the honest second half of it, because a binding naming nothing is a
    run that will fail at submission with a message from the provider rather than
    from here.

    The existence check is one `BatchGetItem` over the whole binding map, so a
    run with three references and an input plate costs one extra read.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("bindings must be an object of name -> node ids")

    wanted: list[str] = []
    for name, value in raw.items():
        entries = value if isinstance(value, list) else [value]
        for index, entry in enumerate(entries):
            if not isinstance(entry, str) or not entry:
                raise ValidationError(f"bindings.{name}[{index}] must be a node id")
            if URL_SCHEME.match(entry):
                raise _InvalidBinding(
                    f"bindings.{name}[{index}] is a URL; bindings name nodes. "
                    "S3 is the only origin."
                )
            wanted.append(entry)

    found = catalog.records(wanted)
    for name, value in raw.items():
        for index, entry in enumerate(value if isinstance(value, list) else [value]):
            node = found.get(entry)
            if node is None:
                raise ValidationError(f"bindings.{name}[{index}] names no node")
            if node["lib"] != lib:
                raise ValidationError(f"bindings.{name}[{index}] is in another library")

    return {name: (value if isinstance(value, list) else [value]) for name, value in raw.items()}


class _InvalidBinding(Exception):
    """A URL where a node id belongs. Caught at the route to answer with a code."""


def _document(folder_id: str, name: str, text: str, owner) -> dict:
    """One payload document: a node, its bytes, and the length actually encoded.

    The node is created first because its id is what names the key — the same
    ordering the upload routes use, for the same reason. `set_blob` then records
    the length that was encoded rather than `len(text)`, which counts characters
    and would be wrong for anything non-ASCII.

    `text/plain` and not `application/json`, deliberately: the frontend shows
    these as text and never decodes them, and a JSON content type is an invitation
    to a browser — or a future contributor — to do exactly that.
    """
    node = catalog.create_node(folder_id, name, catalog.KIND_FILE, owner=owner)
    payload = text.encode()
    s3.put_text(node["blob_key"], payload, "text/plain; charset=utf-8")
    return catalog.set_blob(
        node["node_id"],
        node["blob_key"],
        size=len(payload),
        content_type="text/plain; charset=utf-8",
    )


@bp.post("/runs")
def create_run():
    """Record a run before it is submitted, so a timeout still leaves a record.

    **Before the submission, and that is the whole ordering.** `request.json` and
    `result.json` were two writes for this reason, and they are two calls here: a
    prediction that times out, or a process that is killed, leaves an envelope
    saying `pending` with the exact input beside it rather than nothing at all.

    One transaction writes the envelope, the project's listing row, the character
    usage rows, the run's folder and its `output/` folder. The payload documents
    are S3 writes and cannot be in it — so a failure part-way leaves a run folder
    holding fewer children than it should, which is a visible, re-runnable state.
    """
    body = support.body()
    held = support.memberships()

    project = project_routes.project_at(body.get("project") or "", held)

    kind = body.get("kind")
    if kind not in RUN_KINDS:
        raise ValidationError(f"kind must be one of {', '.join(sorted(RUN_KINDS))}")
    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise ValidationError("model is required")

    characters = body.get("characters") or []
    if not isinstance(characters, list):
        raise ValidationError("characters must be a list")
    for char_id in characters:
        support.entity_at(catalog.ENTITY_CHARACTER, g.library, char_id, held)

    try:
        bindings = validate_bindings(body.get("bindings"), project["lib"])
    except _InvalidBinding as refusal:
        return support.structured("invalid_binding", str(refusal), 400)

    parent = project_routes.folder_for(project, layout.RUN_PARENT)
    record = catalog.create_project_entity(
        KIND,
        project["lib"],
        project["id"],
        parent["node_id"],
        # A run has no slug. Its folder is named for its id — see
        # `create_project_entity`, which spells out why the old
        # `<timestamp>_<hint>` label was a worse copy of `created`.
        slug=None,
        attributes={
            "status": "pending",
            "kind": kind,
            "engine": body.get("engine"),
            "model": model,
            "prediction_id": None,
            "submitted": None,
            "completed": None,
            "bindings": bindings,
            "characters": characters,
            "outputs": [],
            "lineage": body.get("lineage") or {"from_run": None, "from_output": None},
            "cost": None,
            "error": None,
            "payload": {"request": None, "response": None, "prompt": None},
        },
        listing={"status": "pending", "model": model, "kind": kind},
        subfolders=(layout.OUTPUT_FOLDER,),
    )

    payload = _write_payload(record, body)
    if payload:
        record = catalog.update_project_entity(KIND, record, {"payload": payload})

    return jsonify(
        {
            "id": record["id"],
            "status": record["status"],
            "folder": record["folder"],
            "payload": record["payload"],
            "created": record["created"],
        }
    ), 201, {"Location": f"/api/runs/{record['id']}"}


def _write_payload(record: dict, body: dict) -> dict:
    """`request.json` and, when there is one, the prompt — stored, never read.

    The size cap is `config.max_text_bytes` and it is checked on the encoded
    bytes: anything larger is not a request document, it is an output, and it
    belongs on a presigned PUT.
    """
    owner = catalog.blob_owner_for(record["folder"])
    payload = dict(record["payload"])

    documents = {}
    if body.get("input") is not None:
        documents["request.json"] = json.dumps(
            {"model": record["model"], "input": body["input"]}, indent=2, sort_keys=True
        )
    prompt = body.get("prompt")
    if isinstance(prompt, str) and prompt:
        documents["prompt.txt"] = prompt
    elif prompt is not None:
        documents["prompt.json"] = json.dumps(prompt, indent=2, sort_keys=True)

    total = sum(len(text.encode()) for text in documents.values())
    if total > config.max_text_bytes():
        raise ValidationError(
            f"the payload documents must total at most {config.max_text_bytes()} bytes"
        )

    for name, text in documents.items():
        node = _document(record["folder"], name, text, owner)
        payload["request" if name.startswith("request") else "prompt"] = node["node_id"]
    return payload


@bp.get("/runs")
def list_runs():
    """The query that replaces `runs find`.

    `?character=` is one `by-sk` query. `?project=` is one range query on the
    project's listing rows. Neither given walks the library's projects and asks
    each — which is what `runs find` did for *every* query, reading three JSON
    documents per run on the way.

    `status`, `model`, `kind` and `since` filter in memory over one query's worth
    of rows. A GSI per filter would be four indexes for one screen.
    """
    held = support.memberships()
    support.member_of(g.library, held)
    args = request.args

    if args.get("character"):
        character = support.entity_at(
            catalog.ENTITY_CHARACTER, g.library, args["character"], held
        )
        runs = catalog.runs_for_character(character["id"])
    elif args.get("project"):
        project = project_routes.project_at(args["project"], held)
        runs = catalog.project_entities(project["id"], KIND)
    else:
        runs = []
        for project in catalog.entities_in(g.library, catalog.ENTITY_PROJECT):
            runs.extend(catalog.project_entities(project["id"], KIND))
        runs.sort(key=lambda run: run.get("created") or "", reverse=True)

    for field in ("status", "model", "kind"):
        if args.get(field):
            runs = [run for run in runs if run.get(field) == args[field]]
    if args.get("since"):
        runs = [run for run in runs if (run.get("created") or "") >= args["since"]]

    limit = _limit(args.get("limit"))
    offset = _limit(args.get("cursor")) or 0
    window = runs[offset : offset + limit] if limit else runs[offset:]

    thumbs = catalog.records(
        [run["thumb"] for run in window if isinstance(run.get("thumb"), str)]
    )
    for run in window:
        node = thumbs.get(run.get("thumb") or "")
        if node and node.get("blob_key"):
            run["thumb"] = {"node": node["node_id"], "url": s3.presign(node["blob_key"])}
        elif "thumb" in run:
            run["thumb"] = None

    next_offset = offset + len(window)
    return jsonify(
        {"runs": window, "cursor": str(next_offset) if next_offset < len(runs) else None}
    ), 200


def _limit(raw) -> int:
    if raw in (None, ""):
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("limit and cursor must be integers") from None
    if value < 0:
        raise ValidationError("limit and cursor must not be negative")
    return value


def _run(run_id: str, held: dict) -> dict:
    return support.entity_at(KIND, g.library, run_id, held)


@bp.get("/runs/<run_id>")
def get_run(run_id: str):
    """The envelope, with bindings and outputs expanded and payload left as ids.

    **`payload` stays three node ids.** They are fetched as text through
    `GET /api/nodes/<id>/text` by whoever wants them, which is where the "never
    decoded" rule is enforced by there being no code path that could.
    """
    held = support.memberships()
    record = _run(run_id, held)

    node_ids = [node for entries in record.get("bindings", {}).values() for node in entries]
    node_ids += record.get("outputs") or []
    nodes = catalog.records(node_ids)

    def expand(ids):
        return [support.asset(node_id, nodes.get(node_id)) for node_id in ids]

    return jsonify(
        {
            **record,
            "bindings": {
                name: expand(entries) for name, entries in record.get("bindings", {}).items()
            },
            "outputs": expand(record.get("outputs") or []),
        }
    ), 200


@bp.patch("/runs/<run_id>")
def update_run(run_id: str):
    """Move a run forward: submitted, succeeded, failed, cancelled.

    **No `rev`, and that is deliberate.** A character is edited by a person, twice
    at once, and losing somebody's paragraph is the failure optimistic concurrency
    exists to prevent. A run is written by the machine that submitted it, in a
    fixed sequence, and the only concurrent writer is a second attempt at the same
    transition.

    The listing row is updated in the same transaction when `status` changes, so a
    grid never shows `pending` for a run whose envelope says `succeeded`.
    """
    body = support.body()
    held = support.memberships()
    record = _run(run_id, held)

    assignments = {}
    listing = {}
    if "status" in body:
        if body["status"] not in catalog.RUN_STATUSES:
            raise ValidationError(
                f"status must be one of {', '.join(sorted(catalog.RUN_STATUSES))}"
            )
        assignments["status"] = body["status"]
        listing["status"] = body["status"]
    for field in ("prediction_id", "submitted", "completed", "error", "cost", "lineage"):
        if field in body:
            assignments[field] = body[field]

    if not assignments:
        raise ValidationError("nothing to change")
    return jsonify(catalog.update_project_entity(KIND, record, assignments, listing)), 200


@bp.post("/runs/<run_id>/outputs")
def add_output(run_id: str):
    """A placeholder node under the run's `output/`, and a presigned PUT for it.

    **The bytes never transit the Lambda.** The same grant `POST /api/nodes/<id>/
    upload-url` issues — one key, one exact length, one content type — because it
    is the same signature; a video would blow the 6 MB request limit otherwise.

    The first output becomes the listing row's thumbnail, which is what lets the
    runs grid draw without reading an envelope per tile.
    """
    body = support.body()
    held = support.memberships()
    record = _run(run_id, held)

    size = body.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValidationError("size must be a non-negative integer")
    if size > config.max_upload_bytes():
        raise ValidationError(f"an output must be at most {config.max_upload_bytes()} bytes")
    content_type = body.get("content_type")
    if not isinstance(content_type, str) or not content_type:
        raise ValidationError("content_type is required")

    folder = layout.folder_under(record["folder"], layout.OUTPUT_FOLDER)
    node = catalog.create_node(
        folder["node_id"],
        body.get("name"),
        catalog.KIND_FILE,
        owner=catalog.blob_owner_for(folder["node_id"]),
    )

    outputs = (record.get("outputs") or []) + [node["node_id"]]
    listing = {} if record.get("outputs") else {"thumb": node["node_id"]}
    catalog.update_project_entity(KIND, record, {"outputs": outputs}, listing)

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


@bp.post("/runs/<run_id>/response")
def add_response(run_id: str):
    """Store the provider's response verbatim as a payload blob.

    Its own route rather than a field on the `PATCH` because it is bytes rather
    than an envelope field, and because it is the half of the run this service is
    forbidden to have an opinion about. It arrives as a string or an object, is
    encoded, and is written — nothing here reads a key inside it.
    """
    body = support.body()
    held = support.memberships()
    record = _run(run_id, held)

    raw = body.get("body")
    if raw is None:
        raise ValidationError("body is required")
    text = raw if isinstance(raw, str) else json.dumps(raw, indent=2, sort_keys=True)
    if len(text.encode()) > config.max_text_bytes():
        raise ValidationError(f"body must be at most {config.max_text_bytes()} bytes")

    node = _document(
        record["folder"], "response.json", text, catalog.blob_owner_for(record["folder"])
    )
    payload = {**(record.get("payload") or {}), "response": node["node_id"]}
    catalog.update_project_entity(KIND, record, {"payload": payload})
    return jsonify({"node": node["node_id"], "payload": payload}), 201


@bp.delete("/runs/<run_id>")
def delete_run(run_id: str):
    """Remove a run. `?files=keep|delete`, keeping by default."""
    held = support.memberships()
    record = _run(run_id, held)

    files = request.args.get("files") or "keep"
    if files not in ("keep", "delete"):
        raise ValidationError("files must be 'keep' or 'delete'")

    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    if result["blob_keys"]:
        s3.delete(result["blob_keys"])
    return jsonify({"id": record["id"], "files": files}), 200
