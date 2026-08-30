"""Runs: one submission to a model, as an envelope studio owns and a blob it does not.

A run used to be a folder named `<ts>_<slug>` holding three JSON documents nobody
was allowed to parse. The consequence was that the app could show a run as a
folder and nothing else, and that `runs find --character` meant listing every
project, listing every run in each, reading `request.json` for each, and
grepping.

**The split that makes a run presentable without making this service a liar:**

| Studio owns (row, validated, queryable) | The provider owns (blob, verbatim) |
|---|---|
| id, project, status, kind, engine, model, prediction id, timings, bindings, characters, folder, outputs, cost, error | the exact `input` sent, the exact response returned |

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

## A run is created when it is PLANNED, not when it is submitted

This is the change that made a run approvable, and it altered what the row
means. `POST /api/runs` used to be called after a person had said yes at a
terminal, so the existence of the row *was* the record of a submission. It is
called when the run is planned now, and the row starts at `draft`.

What that buys is the whole of the feature: a plan that can be read, edited and
linked to before anything bills, and an **approval that is an artifact** rather
than a `y` that scrolled off a terminal. `plan_digest` hashes what was approved,
`POST /runs/<id>/approve` records it, and the transition into `pending` is
refused unless the two still agree. Hard rule #2's "re-approve after **any**
edit" stops being a thing a person remembers.

Three consequences are load-bearing and each is defended below:

* `draft` and `discarded` are hidden from listings by default, because a grid
  mixing intentions with submissions is a grid nobody can read;
* a draft is **not counted** in the project's run count — the count is bumped by
  the transition into `pending`, once, guarded by `counted`;
* the images a run binds are `SEND#` rows, ordered, carrying the role and the
  provenance that `bindings` could never hold. `bindings` is still answered, and
  is derived from them.

**It is not a permission boundary.** The CLI and the SPA hold tokens from the
same pool, so an agent can approve a run it wrote. What is enforced is that an
approval names a payload and dies when that payload changes.
"""

import json
import logging
import re

from flask import Blueprint, g, jsonify, request

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import (
    ConflictError,
    NotFoundError,
    UpstreamError,
    ValidationError,
)
from studio_core.routes import projects as project_routes
from studio_core.routes import support
from studio_core.services import catalog, generate, layout, manage

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
    run with three references and one input image costs one extra read.
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


def validate_sends(raw, lib: str) -> list[dict]:
    """The ordered images a run binds, each with what it is FOR and where it came from.

    **The same three checks `validate_bindings` makes, because a send is a
    binding that remembers why.** A URI scheme is hard rule #3; a node that does
    not exist is a run that would fail at the provider rather than here; a node
    in another library is somebody else's file. One `BatchGetItem` over the whole
    list, so a run with six references costs one extra read.

    `role` is validated against `catalog.SEND_ROLES` and `source` is not. The
    role decides what the model is given and a wrong one is a different payload;
    `source` is provenance for a reader, is derived rather than authored, and
    gains nothing from a schema this service would then have to keep in step
    with the pipeline's idea of where an image can come from.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("sends must be a list")

    entries = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(f"sends[{index}] must be an object")
        node = entry.get("node")
        field = entry.get("field")
        role = entry.get("role")
        if not isinstance(node, str) or not node:
            raise ValidationError(f"sends[{index}].node must be a node id")
        if URL_SCHEME.match(node):
            raise _InvalidBinding(
                f"sends[{index}].node is a URL; a send names a node. "
                "S3 is the only origin."
            )
        if not isinstance(field, str) or not field:
            raise ValidationError(f"sends[{index}].field must name a model input")
        if role is not None and role not in catalog.SEND_ROLES:
            raise ValidationError(
                f"sends[{index}].role must be one of "
                f"{', '.join(sorted(catalog.SEND_ROLES))}"
            )
        source = entry.get("source")
        if source is not None and not isinstance(source, dict):
            raise ValidationError(f"sends[{index}].source must be an object")
        entries.append({"field": field, "role": role, "node": node,
                        "source": source})

    found = catalog.records([entry["node"] for entry in entries])
    for index, entry in enumerate(entries):
        record = found.get(entry["node"])
        if record is None:
            raise ValidationError(f"sends[{index}].node names no node")
        if record["lib"] != lib:
            raise ValidationError(f"sends[{index}].node is in another library")
        # **Derived here, not reported by the caller**, unless the caller
        # insisted. The pipeline knows why it picked an image, but the pipeline
        # is not the only thing that creates runs and a run reconstructed from
        # history has no `gather` behind it — so provenance is computed from
        # where the node sits, once, and a run submitted today describes its
        # images in the same words as a run backfilled from 2026.
        if entry["source"] is None:
            entry["source"] = catalog.source_of(record)
    return entries


def sends_from_bindings(bindings: dict) -> list[dict]:
    """A `{field: [node, …]}` map read as sends, with the WHY left null.

    **The bridge, and it is deliberately lossy in one direction only.** A caller
    that has not learned to send `sends` still gets ordered rows — the map
    preserves order within a field, and Python preserves the field order the
    caller wrote — so nothing regresses. What it cannot supply is `role` and
    `source`, because the map never carried them: deciding an image is a start
    frame happens in `engine/submit.py::gather`, which is on the other side of
    this call.

    A null `role` is honest about that. Guessing one from the field name would
    put the registry in this service, which has no registry and must not grow
    one — `models.json` is the pipeline's, and a second copy of it here is a
    second answer to what a model accepts.
    """
    return [
        {"field": field, "role": None, "node": node, "source": None}
        for field, nodes in (bindings or {}).items()
        for node in nodes
    ]


def bindings_of(send_entries: list[dict], record: dict | None = None) -> dict:
    """Sends read back as the `{field: [node, …]}` map every client already draws.

    **Derived, so there is only one truth.** The map was an attribute until the
    send rows existed; keeping both would be two spellings of one relationship,
    which is the failure the entity model exists to end. The response shape does
    not change, so no client had to be touched on the day this landed.

    **A run with no send rows falls back to the stored attribute, and that is not
    a courtesy — it is every run that existed before this.** Every one of them
    carries `bindings` and no `SEND#` row, so deriving unconditionally would have
    answered `{}` for the whole library: a run page reading "Nothing was bound"
    over a generation that plainly bound six images. The fallback retires itself
    — `catalog backfill-plans` raises the rows, and after it there is nothing
    left for this branch to answer.
    """
    out: dict[str, list[str]] = {}
    for entry in send_entries:
        out.setdefault(entry["field"], []).append(entry["node"])
    if not out and record:
        stored = record.get("bindings") or {}
        return {name: (value if isinstance(value, list) else [value])
                for name, value in stored.items()}
    return out


def _source_for(node_id: str, record: dict | None) -> dict:
    """Where one image came from, for a send row that did not record it.

    A node the catalog cannot find still gets an answer rather than an error:
    the send genuinely points at it, and a run whose reference was deleted has
    to stay openable.
    """
    if record is None:
        return {"kind": "object"}
    return catalog.source_of(record)


def digest_of(record: dict, send_entries: list[dict] | None = None) -> str:
    """The digest of what this run would send, as it stands right now.

    Recomputed rather than read off the row wherever a decision depends on it —
    the stored `plan_digest` is a cache for a client to compare against, and a
    gate that trusted its own cache would pass exactly the case it exists to
    catch.
    """
    if send_entries is None:
        send_entries = catalog.sends(record["id"])
    return catalog.plan_digest(record.get("plan"), send_entries)


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
    """Create the run as a **draft**, before anything has been approved.

    **The ordering moved one step earlier and that is the whole feature.** The
    record was always written before the submission, so that a prediction which
    times out still leaves an envelope rather than nothing. It is now written
    before the *approval* too, which is what gives an approval something to be
    attached to: a plan with an address, editable, linkable, and hashable.

    That does mean a row no longer asserts that anything happened, which is why
    a draft is hidden from listings and left out of the project's run count until
    it is submitted. See the module docstring.

    One transaction writes the envelope, the project's listing row, the character
    usage rows, the run's folder and its `output/` folder. The sends and the
    payload documents follow, because neither can be in it — the sends are their
    own rows keyed on an id this transaction is still minting, and the documents
    are S3 writes. A failure part-way leaves a draft holding less than it should,
    which is visible and re-runnable, and which nothing has yet paid for.
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

    # `sends` is what a caller that knows about roles supplies; `bindings` is the
    # older spelling and is read as sends with the WHY left null. Both go through
    # the same node checks, so hard rule #3 is enforced whichever one arrives.
    try:
        if body.get("sends") is not None:
            send_entries = validate_sends(body["sends"], project["lib"])
        else:
            bindings = validate_bindings(body.get("bindings"), project["lib"])
            send_entries = validate_sends(sends_from_bindings(bindings), project["lib"])
    except _InvalidBinding as refusal:
        return support.structured("invalid_binding", str(refusal), 400)

    plan = body.get("plan")
    if plan is not None and not isinstance(plan, dict):
        raise ValidationError("plan must be an object")

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
            "status": "draft",
            "kind": kind,
            "engine": body.get("engine"),
            "model": model,
            # **A FILENAME, NOT AN IDENTITY**, and an envelope field rather than
            # part of the plan. It has to be persisted because the thing that
            # names the output file is now the callback, which arrives with no
            # request body and cannot be told what to call anything — and it is
            # deliberately outside `plan` because `plan_digest` hashes the plan:
            # a rename would otherwise void an approval over something the
            # provider is never sent. `services/generate.py::_output_names`.
            "output_name": body.get("name"),
            # The AUTHORED half. `plan` is studio's own and is validated as a
            # map and no further: which knobs a model has is registry data, the
            # registry is the pipeline's, and a copy of it here would be a
            # second answer to what a model accepts.
            "plan": plan,
            "plan_digest": None,
            "approval": None,
            "counted": False,
            "prediction_id": None,
            "submitted": None,
            "completed": None,
            "characters": characters,
            "outputs": [],
            "cost": None,
            "error": None,
            "payload": {"request": None, "response": None, "prompt": None},
        },
        listing={"status": "draft", "model": model, "kind": kind},
        subfolders=(layout.OUTPUT_FOLDER,),
        # A draft is an intention. Counting it here would make a project report
        # runs nobody bought; `update_run` counts it when it is submitted.
        count=False,
    )

    written = catalog.put_sends(record["id"], send_entries)
    assignments = {"plan_digest": catalog.plan_digest(plan, written)}
    # Projected onto the listing row, which is the whole point of it: comparing
    # payloads used to mean one `GET /api/runs/<id>` per candidate run, so the
    # duplicate-submission guard lived in a per-machine file instead. See
    # `catalog.submission_fingerprint`.
    fingerprint = catalog.submission_fingerprint(model, plan, written)

    payload = _write_payload(record, body)
    if payload:
        assignments["payload"] = payload
    record = catalog.update_project_entity(
        KIND, record, {**assignments, "fingerprint": fingerprint},
        {"fingerprint": fingerprint},
    )

    return jsonify(
        {
            "id": record["id"],
            # Echoed because the caller's next question is about this project —
            # "has anything else here already sent this payload" — and going
            # back for the record to find out which project it just wrote to
            # would be a round trip for something it supplied.
            "project": record["project"],
            "status": record["status"],
            "folder": record["folder"],
            "payload": record["payload"],
            "plan_digest": record["plan_digest"],
            # The duplicate-submission guard's handle. Derived here so the CLI
            # never computes it: `plan_digest` has had three implementations in
            # this repository and one of them silently disagreed.
            "fingerprint": record["fingerprint"],
            "sends": written,
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

    `status`, `model`, `kind`, `fingerprint` and `since` filter in memory over one
    query's worth of rows. A GSI per filter would be five indexes for one screen.

    **`?fingerprint=` is the one that is not for a screen.** It answers "has this
    exact payload already been submitted here", which `engine/ledger.py` kept a
    per-machine file to answer because the alternative was a `GET
    /api/runs/<id>` per candidate. Projected onto the listing row it is one
    query — and unlike the file it sees a second machine, and a colleague.
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

    for field in ("status", "model", "kind", "fingerprint"):
        if args.get(field):
            runs = [run for run in runs if run.get(field) == args[field]]
    if args.get("since"):
        runs = [run for run in runs if (run.get("created") or "") >= args["since"]]

    # **Drafts and discards are hidden unless they are asked for**, and this has
    # to come after the filters so that `?status=draft` can still name one. A run
    # is created when it is planned now, so a grid that showed everything would
    # mix intentions with submissions — and the thing a person opens the runs
    # screen to see is what was actually made.
    if not args.get("status") and args.get("include") != "drafts":
        runs = [run for run in runs
                if run.get("status") not in catalog.HIDDEN_RUN_STATUSES]

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


@bp.get("/runs/resolve")
def resolve_run():
    """A runref — what a person types — to the run it names.

    **The sibling of `GET /api/resolve?path=`, and it exists for the same
    reason.** That route turns a slash-joined name path into a node id so a
    person's spelling of a location keeps working as an *address* while ceasing
    to be a key. A runref is the same category of thing: `<project>/latest` is
    how every skill in this repo tells somebody to name the run they just made,
    and until now only the CLI could read one.

    The grammar, which is the whole of it:

        <project>/latest    the newest run there
        <project>/latest#2  its 2nd output, 1-based; absent means every output
        latest              when the project is named separately
        run-<uuid>          the id, which needs no project at all

    **`latest` is one query with `limit=1`**, not a listing filtered down. The
    CLI read every run in the project and took the first, which is a page of rows
    to answer a question about one of them — cheap on a young project and not on
    a busy one.

    **A run has no name, and that is why the grammar stops here.** It had a slug
    once; every one in production read `<timestamp>_<hint>`, so it was unique
    only by embedding `created` — which is what sorting already reads. Strip the
    timestamp and 29 runs collapsed to 19 labels. So a run is found by `latest`,
    by its id, or by the filters on `GET /api/runs`.
    """
    held = support.memberships()
    support.member_of(g.library, held)

    ref = (request.args.get("ref") or "").strip()
    if not ref:
        raise ValidationError("ref is required")

    body, _, raw_index = ref.partition("#")
    index = None
    if raw_index:
        if not raw_index.isdigit() or int(raw_index) < 1:
            raise ValidationError(
                f"runref index must be a positive integer: {ref!r}")
        index = int(raw_index)

    if "/" in body:
        project_ref, _, run_ref = body.partition("/")
    else:
        project_ref, run_ref = request.args.get("project"), body

    if run_ref.startswith("run-"):
        record = _run(run_ref, held)
    else:
        if not project_ref:
            raise ValidationError(
                f"runref {ref!r} has no project and none was supplied — "
                "use <project>/latest, a run id, or pass ?project=")
        if run_ref not in ("latest", "last"):
            raise ValidationError(
                f"{run_ref!r} is not a runref. A run has no name to address it "
                "by — use 'latest', or its id.")
        # **A bare slug, because that is what a person types.** Every other
        # route takes an id or an explicit `slug:<slug>`; a runref's project
        # segment is neither, and requiring the prefix would mean typing
        # `slug:porch-teaser/latest` — which nobody does and no skill documents.
        # This route exists precisely to accept the human spelling.
        addressed = (project_ref if project_ref.startswith("proj-")
                     else f"slug:{project_ref}")
        project = project_routes.project_at(addressed, held)
        # **Drafts are skipped unless asked for**, exactly as `GET /api/runs`
        # skips them, and for the same reason: `latest` is overwhelmingly asked
        # in order to chain off something — `--start-run <project>/latest` — and
        # a draft has no output to chain from. `?include=drafts` opts in, which
        # is the spelling the listing already uses.
        newest = catalog.project_entities(project["id"], KIND)
        hidden = (frozenset() if request.args.get("include") == "drafts"
                  else catalog.HIDDEN_RUN_STATUSES)
        live = [entry for entry in newest if entry.get("status") not in hidden]
        if not live:
            raise NotFoundError(f"no runs in project {project_ref}")
        record = _run(live[0]["id"], held)

    send_entries = catalog.sends(record["id"])

    # **`index` is REPORTED, not applied**, and that is deliberate. Narrowing
    # `outputs` here would look helpful and be wrong for the caller that needs it
    # most: `resolve_output_nodes` filters by extension first — "give me the mp4
    # this run made" — and *then* takes the Nth of what is left. An API that had
    # already dropped the others would silently change which file `#2` means.
    #
    # So resolution answers "what does this string name", and selecting one
    # output stays with whoever knows what they are selecting for.
    return jsonify({**view(record, send_entries), "ref": ref, "index": index}), 200


@bp.get("/runs/<run_id>")
def get_run(run_id: str):
    """The envelope, bindings and outputs expanded, payload left as ids, and the
    way back up.

    `scenes` is which scenes bound this run into a shot, which could not be asked
    before the edge rows existed: it lived in a shot attribute, and `by-sk`
    cannot see into one.

    **`payload` stays three node ids.** They are fetched as text through
    `GET /api/nodes/<id>/text` by whoever wants them, which is where the "never
    decoded" rule is enforced by there being no code path that could.
    """
    held = support.memberships()
    record = _run(run_id, held)
    return jsonify(view(record)), 200


def view(record: dict, send_entries: list[dict] | None = None) -> dict:
    """**One shape for a run, answered by every route that returns one.**

    It was inline in `get_run`, and the four write routes each hand-rolled a
    smaller version — `{**updated, "sends": send_entries}` — carrying the RAW
    send rows and the raw record. The SPA swaps a write's response straight into
    the page rather than re-reading (the whole point: a re-GET would re-sign
    every URL to show one badge change), so a save left the filmstrip drawing
    four "not rendered" placeholders over images that were right there. Seen on
    a dev stack, not reasoned about.

    `sends` may be passed in when the caller has just written them and holds the
    authoritative list; otherwise it is read.
    """
    send_entries = catalog.sends(record["id"]) if send_entries is None else send_entries
    bindings = bindings_of(send_entries, record)
    node_ids = [entry["node"] for entry in send_entries]
    node_ids += [node for entries in bindings.values() for node in entries]
    node_ids += record.get("outputs") or []
    nodes = catalog.records(node_ids)

    def expand(ids):
        return [support.asset(node_id, nodes.get(node_id)) for node_id in ids]

    return (
        {
            # The three authored fields are always present, `None` included. An
            # attribute cleared to `None` is REMOVEd from the row, so a record
            # read back has no key at all — and a client would have to tell
            # "absent" from "null" to draw the difference between a run with no
            # plan and one whose plan was cleared. There is no difference.
            "plan": None,
            "plan_digest": None,
            "approval": None,
            **record,
            "scenes": support.holders(record["id"], catalog.ENTITY_SCENE),
            # **The ordered list, each image with what it is for and where it
            # came from.** This is the half `bindings` never held: the map says
            # an image was sent, and a send says it was the start frame, or the
            # third face reference of a named character.
            "sends": [
                {**entry,
                 # **Derived on read when the row has none**, which is every
                 # send `catalog backfill-plans` wrote: it runs outside this
                 # service and cannot call `source_of`, and a second
                 # implementation of provenance in the pipeline would be a
                 # second dialect — the exact thing deriving it was for. So the
                 # rows carry what only the pipeline knew (field, role, order)
                 # and this fills in what only the catalog knows.
                 "source": entry.get("source")
                 or _source_for(entry["node"], nodes.get(entry["node"])),
                 **support.asset(entry["node"], nodes.get(entry["node"]))}
                for entry in send_entries
            ],
            # Derived from the sends rather than stored, so the two cannot
            # disagree. The shape is unchanged, which is why nothing that drew a
            # run had to be touched.
            "bindings": {
                name: expand(entries) for name, entries in bindings.items()
            },
            "stale": record.get("approval") is not None
            and record["approval"].get("digest") != digest_of(record, send_entries),
            "outputs": expand(record.get("outputs") or []),
        }
    )


# ─────────────────────── the plan, and the gate on it ───────────────────────


def _draftable(record: dict) -> None:
    """A plan may be edited until the run has been submitted, and not after.

    **The refusal is about honesty, not about locking.** Once a prediction has
    gone out, `request.json` records exactly what the provider was given; a plan
    edited afterwards would sit beside it describing something that was never
    sent, and the run page would show the two as though they agreed.
    """
    if record.get("status") not in catalog.UNSUBMITTED_RUN_STATUSES:
        raise ConflictError(
            f"run {record['id']} has been submitted ({record['status']}); "
            "its plan is what was sent and cannot be rewritten"
        )


def _revised(record: dict, assignments: dict, send_entries: list[dict]) -> dict:
    """Write a plan change, recompute the digest, and **drop any approval.**

    This is hard rule #2's "re-approve after **any** edit", made mechanical. It
    was a sentence in a document until now, checked by nobody, and the failure it
    names — approve a payload, edit it, submit the edit — is one that has
    actually happened in this repository.

    Returning the run to `draft` rather than merely clearing `approval` keeps one
    answer to "can this be submitted" instead of two that have to agree.
    """
    plan = assignments.get("plan", record.get("plan"))
    digest = catalog.plan_digest(plan, send_entries)
    # The fingerprint moves with the payload, for the same reason the digest
    # does: an edited draft is a different submission, and a stale fingerprint
    # would make the next identical payload look like a duplicate of it.
    fingerprint = catalog.submission_fingerprint(record.get("model"), plan, send_entries)
    assignments = {**assignments, "plan_digest": digest, "fingerprint": fingerprint,
                   "approval": None, "status": "draft"}
    return catalog.update_project_entity(
        KIND, record, assignments, {"status": "draft", "fingerprint": fingerprint}
    )


@bp.patch("/runs/<run_id>/plan")
def update_plan(run_id: str):
    """Rewrite a draft's authored half. Clears the approval, every time."""
    body = support.body()
    held = support.memberships()
    record = _run(run_id, held)
    _draftable(record)

    plan = body.get("plan")
    if not isinstance(plan, dict):
        raise ValidationError("plan must be an object")

    send_entries = catalog.sends(record["id"])
    updated = _revised(record, {"plan": plan}, send_entries)
    return jsonify(view(updated, send_entries)), 200


@bp.patch("/runs/<run_id>/sends")
def update_sends(run_id: str):
    """Replace the ordered images a draft binds. Clears the approval, every time.

    A replace rather than a merge, because position is the meaning: send 3 is the
    third image the model is handed, and a prompt citing "the first image" makes
    a reorder a real change rather than a cosmetic one.
    """
    body = support.body()
    held = support.memberships()
    record = _run(run_id, held)
    _draftable(record)

    try:
        entries = validate_sends(body.get("sends"), record["lib"])
    except _InvalidBinding as refusal:
        return support.structured("invalid_binding", str(refusal), 400)

    written = catalog.put_sends(record["id"], entries)
    updated = _revised(record, {}, written)
    return jsonify(view(updated, written)), 200


@bp.post("/runs/<run_id>/approve")
def approve_run(run_id: str):
    """Record that a person read this payload and said yes to **this** payload.

    **`digest` is required and is compared, not stored.** The client sends the
    digest of what it just showed somebody; this recomputes the digest of what is
    actually on the row and refuses a mismatch. That is compare-and-swap, and it
    is the difference between an approval and a timestamp: a `y` at a terminal
    said nothing about what it was a yes *to*.

    **This is not a permission boundary and the docstring will not pretend it
    is.** Both halves of studio hold tokens from the same pool, so an agent can
    call this on a run it wrote. What it cannot do is approve one payload and
    send another.

    **`via` records HOW the yes arrived, and exists because the alternative was
    worse.** The CLI had no way to approve without a terminal confirm, on the
    reasoning that an approval flag is the door an agent walks through while
    believing some earlier exchange counted as approval. The absence stopped
    nothing — `yes | studio runs approve …` clears a `click.confirm` — and what
    it produced was a row indistinguishable from a person clicking the button,
    which is the failure the reasoning was trying to prevent. So the door is
    labelled: `relayed` means somebody said yes where this service cannot see it
    and an agent passed it on. It is a WEAKER claim than `interactive`, and a
    reader can finally tell the two apart.
    """
    body = support.body()
    held = support.memberships()
    record = _run(run_id, held)

    if record.get("status") not in ("draft", "approved"):
        raise ConflictError(
            f"run {record['id']} is {record['status']}; only a draft is approved"
        )

    claimed = body.get("digest")
    if not isinstance(claimed, str) or not claimed:
        raise ValidationError("digest is required — approve a payload, not a run")

    send_entries = catalog.sends(record["id"])
    current = digest_of(record, send_entries)
    if claimed != current:
        return support.structured(
            "stale_digest",
            "the plan changed after the payload you approved was rendered; "
            "review it again",
            409,
            digest=current,
        )

    via = body.get("via", "interactive")
    if via not in ("interactive", "relayed"):
        raise ValidationError("via must be 'interactive' or 'relayed'")

    approval = {"by": g.caller_sub, "at": catalog.now(), "digest": current, "via": via}
    updated = catalog.update_project_entity(
        KIND, record, {"approval": approval, "status": "approved"},
        {"status": "approved"},
    )
    return jsonify(view(updated, send_entries)), 200


@bp.delete("/runs/<run_id>/approve")
def revoke_approval(run_id: str):
    """Take an approval back. A draft again, and submittable by nobody."""
    held = support.memberships()
    record = _run(run_id, held)
    if record.get("status") != "approved":
        raise ConflictError(f"run {record['id']} is {record['status']}, not approved")

    updated = catalog.update_project_entity(
        KIND, record, {"approval": None, "status": "draft"}, {"status": "draft"}
    )
    return jsonify(view(updated)), 200


@bp.patch("/runs/<run_id>")
def update_run(run_id: str):
    """Move a run forward: submitted, succeeded, failed, cancelled.

    **The transition into `pending` is the gate, and it is here rather than in
    the CLI on purpose.** The API is the only thing both halves of studio pass
    through — the same argument that moved hard rule #3 out of the pipeline's
    `runs.py` and into this module. A check the CLI made alone would be a rule
    the SPA did not have.

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
    bump_count = False
    if "status" in body:
        if body["status"] not in catalog.RUN_STATUSES:
            raise ValidationError(
                f"status must be one of {', '.join(sorted(catalog.RUN_STATUSES))}"
            )
        # **The gate is on LEAVING the unsubmitted set, not on reaching
        # `pending`, and the difference is the whole of it.** `engine/submit.py`
        # writes `running` when it does not poll and `succeeded` when it does; it
        # never passes through `pending` at all. A check that named one status
        # would have been a gate the only caller walks straight past — enforced
        # in the tests, refused by nothing in practice.
        leaving = (
            record.get("status") in catalog.UNSUBMITTED_RUN_STATUSES
            and body["status"] not in catalog.UNSUBMITTED_RUN_STATUSES
            # An adoption is not a submission. It files an artifact that already
            # existed, calls no provider and bills nothing, so there is no
            # payload for anybody to have approved.
            and body["status"] != catalog.ADOPTED
        )
        if leaving:
            refusal = _refuse_submission(record)
            if refusal is not None:
                return refusal
            # **Counted here, once, because this is where a run stops being an
            # intention.** A draft is created uncounted; without this a project
            # would report zero runs however many it had actually made.
            bump_count = not record.get("counted")
            if bump_count:
                assignments["counted"] = True
            assignments.setdefault("submitted", catalog.now())
        assignments["status"] = body["status"]
        listing["status"] = body["status"]
    for field in ("prediction_id", "submitted", "completed", "error", "cost"):
        if field in body:
            assignments[field] = body[field]

    if not assignments:
        raise ValidationError("nothing to change")

    return jsonify(
        catalog.update_project_entity(KIND, record, assignments, listing,
                                      bump_count=bump_count)
    ), 200


def _refuse_submission(record: dict):
    """The one check that makes hard rule #2 enforceable. `None` means go ahead.

    Called only when a run is leaving the unsubmitted set — a run already
    `running` or `succeeded` moves on freely, because that is the machine
    reporting what a prediction did rather than anybody asking to spend money.

    Two refusals, and they fail differently because a client acts on them
    differently: `not_approved` means show the payload and ask, `stale_digest`
    means the payload moved after somebody said yes and has to be read again.

    **The digest is recomputed here rather than trusted off the row.** A gate
    that read its own cached answer would pass exactly the case it exists to
    catch — a plan written by some path that forgot to update `plan_digest`.
    """
    if record.get("status") != "approved":
        return support.structured(
            "not_approved",
            f"run {record['id']} is {record.get('status')} and has not been "
            "approved; nothing may be submitted without approval of the full "
            "payload",
            409,
        )
    approval = record.get("approval") or {}
    current = digest_of(record)
    if approval.get("digest") != current:
        return support.structured(
            "stale_digest",
            "the payload changed after it was approved; review and approve it "
            "again before submitting",
            409,
            digest=current,
        )
    return None


@bp.post("/runs/<run_id>/submit")
def submit_run(run_id: str):
    """Send an approved run to the provider. **The route that spends money.**

    **This is what moved.** Until now the CLI held the Replicate token, built the
    presigned URLs, created the prediction and sat in a poll loop until it
    settled — so a 15-minute video meant a terminal nobody could close, a killed
    process left a run wedged at `pending`, and the SPA could not submit at all
    because it had no credential and no way to wait. The provider work is here
    now, the wait is a webhook, and both halves of studio reach it the same way.

    The order below is the whole of the safety and none of it is incidental:

    1. **Refuse an already-submitted run**, before anything else. A second POST
       to this route is the cheapest way to buy the same prediction twice.
    2. **Check the approval and the digest** — `_refuse_submission`, the same
       function `PATCH /api/runs/<id>` uses, so there is one answer to "may this
       be sent" rather than two that have to agree.
    3. **Preflight the payload while the run is still `approved`.** A model that
       will refuse the input must leave the run exactly as it was — editable,
       approvable, submittable again — rather than at `pending` with nothing
       behind it.
    4. **Move to `pending`, then call the provider.** The gate stands in front of
       the money rather than behind it, and a process that dies in between leaves
       a run that reads as "went out and never answered" rather than as a draft.

    The response says which of the two closing triggers this submission got.
    `callback: "webhook"` means Replicate will call back and the caller should
    watch the row; `callback: "poll"` means nothing can reach this API from the
    internet — local development — and the caller drives
    `POST /api/runs/<id>/reconcile` itself. See `services/generate.py`.
    """
    held = support.memberships()
    record = _run(run_id, held)

    if record.get("status") not in catalog.UNSUBMITTED_RUN_STATUSES:
        raise ConflictError(
            f"run {record['id']} is {record['status']}; it has already been sent"
        )

    refusal = _refuse_submission(record)
    if refusal is not None:
        return refusal

    send_entries = catalog.sends(record["id"])
    # Before `pending`, deliberately. See point 3 above.
    entry, payload, bindings = generate.prepare(record, send_entries)

    bump_count = not record.get("counted")
    record = catalog.update_project_entity(
        KIND,
        record,
        {"status": "pending", "submitted": catalog.now(), "counted": True},
        {"status": "pending"},
        bump_count=bump_count,
    )

    created = generate.dispatch(record, entry, payload, bindings)
    prediction_id = created.get("id")
    if not prediction_id:
        # The provider answered and named no prediction. Nothing is in flight, so
        # unlike a transport failure this one is knowable and is recorded as the
        # failure it is.
        record = catalog.update_project_entity(
            KIND, record,
            {"status": "failed", "completed": catalog.now(),
             "error": "the provider returned no prediction id"},
            {"status": "failed"},
        )
        raise UpstreamError("the provider returned no prediction id")

    record = catalog.update_project_entity(
        KIND, record, {"status": "running", "prediction_id": prediction_id},
        {"status": "running"},
    )
    return jsonify({
        **view(record, send_entries),
        "callback": "webhook" if generate.callback_url(run_id) else "poll",
    }), 200


@bp.post("/runs/<run_id>/reconcile")
def reconcile_run(run_id: str):
    """Ask the provider what happened to this run's prediction, and close it.

    **Two situations, one shape, and that is not a coincidence being papered
    over.** In local development Replicate cannot reach `http://localhost:8000`,
    so there was never going to be a callback; in production a callback can be
    lost to a deploy landing mid-flight or to a signature this service refused.
    From here both are "the run is `running`, the prediction is not, and nothing
    told us" — and the remedy is the same question to the same endpoint.

    It runs the identical closing code the webhook runs, so a run closed either
    way is the same row. Idempotent: a run already finished comes back untouched
    rather than re-uploading its output.

    **Deliberately not a poller.** Nothing schedules this; it is called by a
    caller that is waiting, or by a person who noticed. A sweep over stale
    `running` rows would need a scheduler, a bound and a decision about how old
    is too old, and none of those pay for themselves while the webhook is the
    normal path.
    """
    held = support.memberships()
    record = _run(run_id, held)
    return jsonify(view(generate.reconcile(record))), 200


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

    manage.drain(g.library)
    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    manage.release(g.library, result["blob_keys"], result["sweeps"])
    return jsonify({"id": record["id"], "files": files}), 200
