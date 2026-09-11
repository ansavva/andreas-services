"""`studio runs` — the run store: an envelope in a row, plus the provider's blobs.

A **run** is one submission to a model and everything about it, split in two:

    the row   id, project, status, kind, engine, model, prediction id,
              timings, bindings (NODE IDS), characters, folder, outputs,
              cost, error                             — studio owns and validates
    the blobs request.json, prompt.json, result.json  — the provider owns, and
              studio stores them verbatim and never decodes them

The payload blobs are never decoded: the pipeline changes the payload's shape
freely, so nothing should be invited to parse it. The envelope around them is
studio's own, so it can be queried — `runs find --character` is
`GET /api/runs?character=…`, one query, and `runs list --model/--status/--since`
is three more parameters on the same query. Both are in `adapters/entities.py`,
and this module does not know how either is spelled.

BINDINGS ARE NODE IDS
---------------------
A path is invalidated by any rename or move; a node id survives both by
construction, so a binding is a node id.

**Hard rule #3.** `check_bindings` refuses a URL-shaped binding here, before the
request is sent, so `submit.py` can decline to submit at all — and the API
refuses it again, because the SPA goes through the API too and never through
this function.

ADDRESSING A RUN
----------------
    <project>/latest     the newest run there
    <project>/latest#2   its 2nd output (1-based); default is every output
    latest               when the project is supplied out of band (--project)
    run-<uuid>           the id, which is what a record holds

**A RUN HAS NO SLUG, AND THAT IS THE WHOLE OF ITS ADDRESSING.** A run is a
machine event: it is found by `latest`, by its id, or by the filters below —
`--character`, `--model`, `--status`, `--since`. A human label would only be
unique by embedding `created`, which is what sorting reads and `--since`
filters on already.

A scene and a movie have a slug and title. Those are things a person plans and
comes back to; a run is not.

CLI
---
    studio runs list <project> [--character|--model|--status|--since]
    studio runs find --character <name>
    studio runs show <project>/latest [--payload]
    studio runs outputs <project>/latest --presign
    studio runs edit <project>/latest [--dump|--file -]
    studio runs delete <project>/latest [--files delete]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import click

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import reports

SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
VID_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
#: **There is no `ID_RE`.** An id's prefix is for a person reading a log, and
#: every command that takes one either passes it to the API or tests
#: `startswith("node-")` to tell an id from a name path. A regex that says what
#: an id looks like invites parsing one for meaning.
#:
#: What a send may be FOR. The API is the enforcer and refuses anything else;
#: this is here so `runs edit` can name the four in an error message rather than
#: spending a round trip to be told. `submit.py` assigns them from the registry —
#: `images.start`, `.end`, `.refs`, and `input` for a field the entry does not name.
SEND_ROLES = ("start", "end", "reference", "input")


class RunError(Exception):
    pass


def slugify(slug: str) -> str:
    """A run's human label, cleaned because it becomes a folder name."""
    out = SLUG_RE.sub("-", (slug or "run").strip()).strip("-.")
    return out[:60] or "run"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def dumps(obj) -> str:
    """The one serialization for every payload document.

    `sort_keys=False` is load-bearing rather than a default spelled out: these
    documents are read by people, and the order they were written in is the
    order they should be read in.
    """
    return json.dumps(obj, indent=2, sort_keys=False)


# --- the invariant --------------------------------------------------------

def check_bindings(bindings: dict) -> dict:
    """Bindings map an input field -> the node id(s) bound to it. Ids ONLY.

    Refuses anything URL-shaped: a presigned URL in a stored record is expired
    data plus leaked time-limited access, and it is the one thing hard rule #3
    exists to prevent.

    **It also refuses a path**, which is new and is the point of the change. A
    path was legal here until records named nodes; it is now a stale spelling
    that would resolve today and dangle after the first rename, and accepting it
    silently is exactly how sixty-nine records went bad. The message says what
    to pass instead rather than merely refusing.
    """
    clean: dict = {}
    for field, val in (bindings or {}).items():
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            if not isinstance(v, str):
                raise RunError(f"binding {field!r} must be node id string(s), "
                               f"got {type(v).__name__}")
            if "://" in v or v.startswith("//"):
                raise RunError(
                    f"binding {field!r} looks like a URL, not a node id: {v[:60]}…\n"
                    "Store node ids; presigned URLs are minted fresh at submit time."
                )
            if not v.startswith("node-"):
                raise RunError(
                    f"binding {field!r} is not a node id: {v!r}\n"
                    "Bindings name nodes, not paths — a path is invalidated by any "
                    "rename, which is what left records dangling before."
                )
        clean[field] = vals if isinstance(val, list) else val
    return clean


def presign(nodes: list[str]) -> list[str]:
    """Mint fresh presigned URLs — the ONLY way assets reach Replicate.

    **There is no expiry parameter.** The API signs these against its own
    credentials and owns the TTL (`STUDIO_PRESIGN_TTL_SECONDS`); nothing on this
    side could honour one.
    """
    return [store.presign_node(node) for node in nodes]


# --- human review ---------------------------------------------------------

PROMPT_REF = "<< see document 1/2 — PROMPT >>"


def render_payload(run: str, model: str, endpoint: str, payload: dict,
                   bindings: dict | None = None) -> str:
    """Render a submission for a person to read, as TWO JSON documents.

    **This is hard rule #2's surface and nothing may shorten it.** One combined
    document is unreviewable: `prompt` is itself a serialized JSON object, so
    nesting it inside the payload double-escapes it onto one enormous line.
    Splitting them keeps both as real, indented JSON — the prompt as the
    structured object it is, and the payload as the parameters the model
    receives. It mirrors how a run is stored: prompt.json beside request.json.
    """
    prompt = payload.get("prompt")
    try:  # studio-media-prompt emits a serialized JSON object — show it unpacked
        prompt_doc = json.loads(prompt) if isinstance(prompt, str) else prompt
    except json.JSONDecodeError:
        prompt_doc = prompt  # plain prose prompt; show as-is

    inp = {k: v for k, v in payload.items() if k != "prompt"}
    if prompt is not None:
        inp["prompt"] = PROMPT_REF
    for field, val in (bindings or {}).items():
        inp[field] = ([f"<presigned: {k}>" for k in val] if isinstance(val, list)
                      else f"<presigned: {val}>")

    def dump(o):
        return json.dumps(o, indent=2, ensure_ascii=False)

    return "\n".join([
        "===== 1/2  PROMPT — serialized into the `prompt` string at submit time =====",
        dump(prompt_doc),
        "",
        "===== 2/2  INPUT — the parameters this model receives =====",
        dump({"run": run, "model": model, "endpoint": endpoint, "input": inp}),
    ])


# --- writing a run --------------------------------------------------------

def record_request(
    project: str, *, kind: str, engine: str, model: str,
    input: dict, bindings: dict | None = None, prompt_source: dict | None = None,
    characters: list[str] | None = None, plan: dict | None = None,
    sends: list[dict] | None = None, name: str | None = None,
) -> dict:
    """Create the run as a DRAFT. **Called before the submission.**

    The ordering is the reason `request.json` and `result.json` were two writes
    and is preserved as two calls: a prediction that times out still leaves a
    record, and a store that recorded nothing until success would lose exactly
    the runs worth investigating.

    `project` and each entry in `characters` are ids. Resolving a slug is the
    caller's job, done once, because a caller that has resolved a project
    usually needs the record for something else too.

    **No slug is sent.** A run has none; the API names its folder for its id.
    `name` — `--name` on `studio run` — is what the output FILE is called.

    **`name` is recorded at creation rather than used later** because the
    download happens in the API: the callback that closes a run carries no
    request body, so a filename that is not on the row before the submission is
    a filename nothing can recover.
    """
    clean = check_bindings(bindings or {})
    try:
        return entities.create_run(
            project=project, kind=kind, engine=engine, model=model,
            input=input, bindings=clean, plan=plan, sends=sends,
            characters=characters or [], prompt=prompt_source, name=name)
    except api.ApiError as exc:
        raise RunError(str(exc)) from exc


# **`upload_output` and `record_result` were here, and both are deleted.**
#
# They were the last two steps of `engine/submit.py`: put each downloaded file
# into the run's `output/` folder, then `PATCH` the envelope closed and store the
# provider's response beside it. Both now happen in the API, off a callback, in
# `services/generate.close_from_prediction`.
#
# They are removed rather than left unused, and that is the point rather than
# tidiness. A function here that closes a run would be a **second closing
# implementation** — one reachable from a terminal, writing the same fields in a
# slightly different order, drifting from the one the webhook actually runs. The
# repository has been bitten by exactly that shape before: `plan_digest` had
# three implementations and one of them silently disagreed, reporting 131 healthy
# runs as stale.
#
# What replaced them for a person who needs to close a run by hand is
# `studio runs reconcile`, which asks the API to ask the provider — so the row is
# written by the same code either way.


# --- reading runs ---------------------------------------------------------

def list_runs(project: str, **filters) -> list[dict]:
    """A project's runs, newest first. One query, with the filters free.

    `project` is an id or a `slug:` address; `entities.query_runs` accepts
    either, and the API resolves it. Every filter is a row attribute, so
    `--model`, `--status` and `--since` cost nothing that `--character` did not
    already cost.
    """
    return entities.query_runs(project=project, **filters).get("runs") or []


def find_runs(**filters) -> list[dict]:
    """Runs across every project. What `runs find --character` became."""
    return entities.query_runs(**filters).get("runs") or []


def run_outputs(run_id: str) -> list[dict]:
    """A run's output nodes, in the order the run recorded them.

    **Order is the record's, not a listing's.** A natural sort over `output/`'s
    children would put `-10` before `-2` and hand a later run the wrong frame
    under the right name. The row holds the order the outputs were written in,
    so there is nothing to re-derive.
    """
    return entities.get_run(run_id).get("outputs") or []


def run_record(run_id: str) -> dict:
    """The whole envelope. `payload` names nodes; nothing here opens one."""
    return entities.get_run(run_id)


def payload_documents(record: dict) -> dict[str, str]:
    """The provider documents as raw text, keyed by role.

    **Read, never decoded.** `runs show --payload` prints what comes back
    verbatim; studio does not know whether it is JSON and must not act as
    though it does. A document that is missing is simply absent from the map —
    a run has no response until it finishes, and no prompt unless a structured
    source was used.
    """
    out: dict[str, str] = {}
    for role, node_id in (record.get("payload") or {}).items():
        if not node_id:
            continue
        try:
            out[role] = store.node_text(node_id)
        except api.NotFound:
            continue
    return out


# --- runrefs: addressing a previous run's output --------------------------

def resolve_run(ref: str, default_project: str | None = None) -> dict:
    """A runref -> the run record. **The grammar is the API's now.**

    `<project>/latest`, `latest#2` and `run-<uuid>` are read by
    `GET /api/runs/resolve`, beside `GET /api/resolve?path=` and for the same
    reason: both turn a person's spelling into the thing it names. While the
    parsing lived here only the CLI could read one, and resolving `latest` meant
    listing every run in the project to take the first — a page of rows to answer
    a question about one of them.

    Returns the **record**, not a `(project, id)` pair. Every caller went
    straight on to read the run, and returning a pair meant a second round trip
    plus two more strings to keep in step.

    **The project segment is turned into an id here.** A name is a free-text
    label and the route resolves nothing but ids, so a name costs one listing on
    this side before the ref is sent.
    """
    project, sep, tail = ref.partition("/")
    if sep and not project.startswith("proj-"):
        ref = f"{_project_id(project)}/{tail}"
    try:
        return entities.resolve_run(ref, _address(default_project))
    except api.NotFound as exc:
        raise RunError(str(exc)) from exc
    except api.ApiError as exc:
        # A 400 from the resolver is a malformed runref, which is a person's
        # typo rather than a fault — reported in this module's own vocabulary so
        # `@errors.reports(RunError)` prints it without a traceback.
        raise RunError(str(exc)) from exc


def _address(project: str | None) -> str | None:
    """A project id passed through; a name matched client-side.

    A name is a free-text label and the API will not resolve one, so this costs
    a listing and can refuse an ambiguous name.
    """
    if not project or project.startswith("proj-"):
        return project
    return _project_id(project)


def _character_address(character: str | None) -> str | None:
    """The same, for a character."""
    if not character or character.startswith("char-"):
        return character
    try:
        return P.by_name(entities.list_characters(), character, "character")["id"]
    except P.PathError as exc:
        raise RunError(str(exc)) from exc


def resolve_output_nodes(ref: str, default_project: str | None = None,
                         kinds: set[str] | None = None) -> list[str]:
    """The NODE IDS of a runref's output — what chaining consumes.

    Node ids, not paths: a later run binds these, and a binding that named a
    path would be stranded by any rename of the file it named.
    """
    # **The index is applied AFTER the kind filter**, which is why it comes back
    # from the resolver rather than being acted on there: `#2` means the second
    # mp4 this run made, not the second output that happens to be one.
    record = resolve_run(ref, default_project)
    index = record.get("index")
    outputs = record.get("outputs") or []
    if kinds:
        chosen = [o for o in outputs
                  if os.path.splitext(o.get("name") or "")[1].lower() in kinds]
    else:
        chosen = list(outputs)
    if not chosen:
        have = [os.path.splitext(o.get("name") or "")[1] for o in outputs]
        raise RunError(
            f"run {record['id']} has no output matching {sorted(kinds or [])} "
            f"(it holds {have or 'nothing'})"
        )
    if index is not None:
        if index > len(chosen):
            raise RunError(f"run {record['id']} has {len(chosen)} output(s); "
                           f"asked for #{index}")
        return [_output_node(chosen[index - 1])]
    return [_output_node(o) for o in chosen]


def _output_node(entry: dict) -> str:
    """An output's node id, under either spelling the record may carry.

    A run record read back from the API keys it `id`; older documents key it
    `node`. Reading only one spelling makes every runref binding (`--ref-run`,
    `--image-run`, `--start-run`, `--end-run`, and `add-refs --from-run`) die on
    `KeyError` against the other. `engine/turnaround.py` carries the same
    two-spelling read for the same reason.
    """
    node = entry.get("node") or entry.get("id")
    if not node:
        raise RunError(f"run output carries no node id: {sorted(entry)}")
    return node


# --- legacy import --------------------------------------------------------

def adopt(project: str, node_id: str) -> dict:
    """Wrap a pre-scheme artifact in a synthetic run so history is uniform.

    **A move, and the node keeps its id** — so anything that already named this
    file, a share link included, still names it after adoption. That was already
    true before the entity model; what is new is that the run naming it is a row
    rather than two documents, so the adopted artifact is queryable beside every
    real run.

    The run is created before the move, so a failure leaves a run with no output
    — visible, and re-runnable once the cause is fixed. The other order would
    leave the artifact parented to a folder that was never made.
    """
    try:
        node = store.node(node_id)
    except api.NotFound as exc:
        raise RunError(f"no such node: {node_id}") from exc
    ext = os.path.splitext(node.get("name") or "")[1].lower()
    record = record_request(project,
                            kind="video" if ext in VID_EXTS else "image",
                            engine="(pre-scheme)", model="(unrecorded)",
                            input={}, bindings={})
    output = store.ensure_child_folder(record["folder"], "output")
    store.reparent_node(node_id, output["id"])
    # The node is named on the record explicitly, because reparenting it into
    # `output/` does not put it there — `outputs` is a list the row maintains,
    # not a listing of the folder. That distinction is the whole reason a run's
    # outputs keep the order they were written in.
    entities.patch_run(record["id"], status="adopted", completed=_now(),
                       outputs=[node_id])
    return entities.get_run(record["id"])


# --- CLI ------------------------------------------------------------------

@click.group(help=__doc__)
def main():
    pass


def _row(record: dict) -> str:
    """One listing row. **Every field here is one the projection actually carries.**

    The projection is `{lib, id, created, status, model, kind, thumb}`; a test
    fake that projects off the full record will pass a row that raises
    `KeyError` against the real API. Reading with `.get` where a field is
    optional, and reading nothing that is not projected, is the rule here.
    """
    cost = (record.get("cost") or {}).get("amount")
    return (f"{record['created'][:16]}  {record['id']}  "
            f"{(record.get('model') or ''):<28} {(record.get('kind') or ''):<6} "
            f"{(record.get('status') or ''):<10}"
            + (f"  ${cost}" if cost is not None else ""))


@main.command("list")
@click.argument("project", required=True)
@click.option("--character", help="Only runs that used this character.")
@click.option("--json", "json_", is_flag=True)
@click.option("--model", help="Only runs on this model (e.g. google/nano-banana-pro).")
@click.option("--since", help="Only runs created at or after this ISO timestamp.")
@click.option("--status", help="pending | running | succeeded | failed | cancelled.")
@reports(RunError, api.ApiError)
def do_list(project, character, json_, model, since, status):
    """A project's runs, newest first. Every filter is one query, not a walk."""
    found = list_runs(
        _address(project),
        character=_character_address(character),
        model=model, status=status, since=since)
    if json_:
        print(json.dumps(found, indent=2))
    else:
        print("\n".join(_row(r) for r in found) or f"(no runs in {project})")


@main.command("find")
@click.option("--character", required=True)
@click.option("--json", "json_", is_flag=True)
@click.option("--project", multiple=True, help="Limit to these projects. Repeatable.")
@reports(RunError, api.ApiError)
def do_find(character, json_, project):
    """Every run that used a character, across every project.

    **One API query.** `--project` is a filter applied to that query.
    """
    address = _character_address(character)
    if project:
        hits = [r for p in project for r in find_runs(character=address,
                                                      project=_address(p))]
    else:
        hits = find_runs(character=address)
    if json_:
        print(json.dumps(hits, indent=2))
    else:
        print("\n".join(_row(r) for r in hits) or f"(no runs recorded {character})")


@main.command("show")
@click.argument("runref", required=True)
@click.option("--payload", is_flag=True,
              help="Also print the provider documents, verbatim and undecoded.")
@click.option("--project", help="Default project for a bare run slug.")
@reports(RunError, api.ApiError)
def do_show(runref, payload, project):
    """One run's envelope — and, with --payload, the documents studio never reads."""
    record = resolve_run(runref, project)
    print(json.dumps({k: v for k, v in record.items() if k != "payload"}, indent=2))
    if not payload:
        return
    for role, text in payload_documents(record).items():
        # Printed as it came back. Not re-serialised, not pretty-printed, not
        # parsed: the provider owns the shape of these and studio's only
        # promise about them is that it stored what it was given.
        print(f"\n===== {role} — as the provider wrote it =====")
        print(text)


@main.command("outputs")
@click.argument("runref", required=True)
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
@click.option("--project", help="Default project for a bare run slug.")
@reports(RunError, api.ApiError)
def do_outputs(runref, json_, presign, project):
    """`--presign` reaches `store` directly, deliberately.

    The flag is named `presign` and so is this module's function, so inside this
    body the flag shadows it — calling `presign(...)` here would call `True`.
    Renaming the parameter is not available: `cli_surface_reference.json`
    records the dest, and it is a contract. Doing the work inline is.
    """
    nodes = resolve_output_nodes(runref, project)
    vals = [store.presign_node(n) for n in nodes] if presign else nodes
    print(json.dumps(vals, indent=2) if json_ else "\n".join(vals))


@main.command("delete")
@click.argument("runref", required=True)
@click.option("--files", type=click.Choice(["keep", "delete"]), default="keep",
              help="What to do with the run's folder (default: keep it).")
@click.option("--project", help="Default project for a bare run slug.")
@reports(RunError, api.ApiError)
def do_delete(runref, files, project):
    """Delete one run: the envelope, and with `--files delete` its folder too.

    **The runref is resolved first and the id is printed back**, because
    `latest` is the spelling anyone reaching for this will use and it names a
    different run tomorrow. What was deleted has to be legible after the fact,
    and a resolved id is the only thing that stays true.

    **`--files keep` is the default, matching `projects delete`.** The reverse
    default loses generated media to a typo; a folder orphaned into the library
    root is visible and can still be moved or removed by hand. Against
    production the delete is a recoverable tombstone — the API's role holds no
    `s3:DeleteObjectVersion` — but that is the deployed service's protection,
    not this command's, and it does not apply to a dev stack.

    Nothing cascades. A run holds no entities; a scene shot that names this run
    keeps the id, and there is no check here that finds one.
    """
    record = resolve_run(runref, project)
    entities.delete_run(record["id"], files=files)
    print(f"deleted run {record['id']} (files: {files})")


#: The editable half of a draft, and the whole of it. `source` is absent because
#: it is DERIVED — the API recomputes it from where each node sits and excludes it
#: from the digest, so offering it for editing would offer a field that neither
#: changes the payload nor survives the write.
EDITABLE = ("prompt", "params", "note", "sends")


def editable(record: dict) -> dict:
    """A draft as the document `runs edit` hands to an editor.

    Flat rather than nested under `plan`, because the two halves are patched
    through two different routes and a person editing one should not have to know
    that. What comes back is split again by `_apply_edit`.

    **A send is `field`, `role` and `node` — the three fields the digest hashes.**
    The names of the pictures are printed above the editor instead of being
    carried in here: a name is a caption, editing one would mean nothing, and a
    document whose keys are not all writable is a document that lies.
    """
    plan = record.get("plan") or {}
    return {
        "prompt": plan.get("prompt"),
        "params": plan.get("params") or {},
        "note": plan.get("note"),
        "sends": [{"field": send.get("field"), "role": send.get("role"),
                   "node": send.get("node")}
                  for send in record.get("sends") or []],
    }


def _validate_edit(doc) -> dict:
    """The shape checks worth making here — the rest are the API's.

    Deliberately shallow. `params` is a map and no further, because which knobs a
    model has is registry data and the field names a send may use are checked
    against the model's live schema by `submit`'s preflight — checking them twice
    means two answers that can disagree, and the one here would be the stale one.
    """
    if not isinstance(doc, dict):
        raise RunError("the document must be a JSON object")
    unknown = [key for key in doc if key not in EDITABLE]
    if unknown:
        raise RunError(f"unknown field(s): {', '.join(sorted(unknown))} "
                       f"(editable: {', '.join(EDITABLE)})")
    params = doc.get("params", {})
    if not isinstance(params, dict):
        raise RunError("params must be an object")
    sends = doc.get("sends", [])
    if not isinstance(sends, list):
        raise RunError("sends must be a list")
    for index, send in enumerate(sends):
        if not isinstance(send, dict):
            raise RunError(f"sends[{index}] must be an object")
        if not isinstance(send.get("node"), str) or not send["node"]:
            raise RunError(f"sends[{index}].node must be a node id")
        if not isinstance(send.get("field"), str) or not send["field"]:
            raise RunError(f"sends[{index}].field must name a model input")
        role = send.get("role")
        if role is not None and role not in SEND_ROLES:
            raise RunError(f"sends[{index}].role must be one of "
                           f"{', '.join(sorted(SEND_ROLES))}, or null")
    return doc


@main.command("edit")
@click.argument("runref", required=True)
@click.option("--file", "source", type=click.File("r"),
              help="Read the edited document from here ('-' for stdin) "
                   "instead of opening an editor.")
@click.option("--dump", is_flag=True,
              help="Print the editable document and change nothing.")
@click.option("--project", help="Default project for a bare runref.")
@reports(RunError, api.ApiError)
def do_edit(runref, source, dump, project):
    """Rewrite a draft's prompt, parameters and images.

    A draft was the one thing in studio that could be read and not changed. The
    routes to change it have existed since the run gained a plan and nothing
    called them, so a prompt with a typo in it meant discarding the draft and
    drafting it again — which is why this exists.

    **An edited draft is a payload nobody has read yet.** Hard rule #2 says
    show it again before submitting; `studio runs show` does, and this command
    ends by saying so.

    The document is the payload and nothing else — `prompt`, `params`, `note`
    and the ordered `sends`. The pictures' names are printed above the editor
    rather than carried inside it: **the order is the meaning** (a prompt citing
    "the first image" is citing this list), and a caption in a document that
    cannot be written to would read as though it could.

    Two routes, so only what moved is written: a prompt edit leaves the send rows
    untouched, and a reorder leaves the plan untouched. A key left out of the
    document is left alone rather than cleared — which is what makes
    `{"prompt": "…"}` a legal thing to pipe in.

        studio runs edit run-<uuid>              # $EDITOR, then patch what changed
        studio runs edit run-<uuid> --dump       # the document, to stdout
        studio runs edit run-<uuid> --file -     # the document back, from stdin
    """
    record = resolve_run(runref, project)
    if record.get("status") != "draft":
        raise RunError(
            f"run {record['id']} is {record.get('status')} and has been "
            f"submitted; its plan is what was sent and cannot be rewritten")

    before = editable(record)
    if dump:
        print(json.dumps(before, indent=2, ensure_ascii=False))
        return

    text = json.dumps(before, indent=2, ensure_ascii=False)
    if source is not None:
        edited = source.read()
    else:
        # Printed before the editor opens, so the pictures the numbers refer to
        # have names while the list is being reordered.
        print(_render_plan(record), file=sys.stderr)
        edited = click.edit(text, extension=".json")
        if edited is None:
            print("nothing saved; unchanged.", file=sys.stderr)
            return

    try:
        after = _validate_edit(json.loads(edited))
    except json.JSONDecodeError as exc:
        # The editor's buffer is gone by now, so the message has to be enough to
        # retype from — and `--file` is the way back in without one.
        raise RunError(f"that is not valid JSON ({exc}); nothing was changed. "
                       f"Retry with: studio runs edit {record['id']}") from exc

    _apply_edit(record, before, after)


def _apply_edit(record: dict, before: dict, after: dict) -> None:
    """Write the halves that moved, and say what that cost.

    Plan first, then sends; the second write is the one whose response is
    current.
    """
    plan_changed = any(before[key] != after.get(key, before[key])
                       for key in ("prompt", "params", "note"))
    sends_changed = before["sends"] != after.get("sends", before["sends"])

    if not plan_changed and not sends_changed:
        print("no changes.")
        return

    if plan_changed:
        plan = {**(record.get("plan") or {}),
                "prompt": after.get("prompt", before["prompt"]),
                "params": after.get("params", before["params"]),
                "note": after.get("note", before["note"])}
        entities.patch_run_plan(record["id"], plan)
    if sends_changed:
        entities.patch_run_sends(record["id"], after.get("sends", before["sends"]))

    what = " and ".join(w for w in ("the plan" if plan_changed else "",
                                    "the images" if sends_changed else "") if w)
    print(f"edited {what} of {record['id']}")
    print(f"read it again with: studio runs show {record['id']}  —  "
          f"then, if told to: studio runs submit {record['id']}")


@main.command("submit")
@click.argument("runref", required=True)
@click.option("--project", help="Default project for a bare runref.")
@reports(RunError, api.ApiError)
def do_submit(runref, project):
    """Send a draft to the model. **This is what bills.**

    **This command is the act, and there is no separate approve step.** Hard
    rule #2 — nothing runs unless a person tells it to — is met by who types
    it: a person who has read the payload (`--dry-run`, or `studio runs show`),
    or an agent that person has explicitly told to send this run. No flag on
    this command stands in for either; a `--yes` was refused for that reason,
    and an approve subcommand that recorded a yes as a row was deleted
    because a recorded yes is not a stronger claim than a typed command.

    The draft is what goes out. It can have been left by `--dry-run`, by
    `scenes board`, or by the app, and it can be read in one place and sent from
    another.
    """
    record = resolve_run(runref, project)
    if record.get("status") != "draft":
        raise RunError(
            f"run {record['id']} is {record.get('status')}, not a draft")
    print(f"submitting {record['id']} …", file=sys.stderr)
    # The engine owns the submit lifecycle; importing it here rather than at the
    # top keeps `domain` free of `engine` at import time, which is the direction
    # the dependency arrow points everywhere else in this package.
    from studio_pipeline.engine import resubmit
    print(json.dumps({k: v for k, v in resubmit.submit_draft(record).items()
                      if k != "payload"}, indent=2))


@main.command("reconcile")
@click.argument("runref", required=True)
@click.option("--project", help="Default project for a bare runref.")
@reports(RunError, api.ApiError)
def do_reconcile(runref, project):
    """Ask the provider what happened to a run's prediction, and close it.

    **For a run that went out and never came back.** A generation is closed by a
    callback now, and a callback can be lost — a deploy landing mid-flight, a
    signature the API refused, a message nobody drained. The run sits at
    `running` with a prediction id: legible, and never resolving. This is what
    resolves it.

    It is also the whole of the story on a machine with no callback receiver
    provisioned, where there was never going to be a callback in the first place.

    **Nothing here decides anything and nothing here bills.** The API asks
    Replicate for the prediction and closes the run with the same code the
    callback consumer runs, so a run closed this way and a run closed by a webhook
    are the same row. Safe to repeat: a run that has already finished comes back
    untouched rather than having its output uploaded twice.
    """
    record = resolve_run(runref, project)
    updated = entities.reconcile_run(record["id"])
    print(json.dumps({k: updated.get(k) for k in
                      ("id", "status", "error", "outputs")}, indent=2))


@main.command("discard")
@click.argument("runref", required=True)
@click.option("--files", type=click.Choice(["keep", "delete"]), default="delete",
              help="What to do with the run's folder (default: delete it).")
@click.option("--project", help="Default project for a bare runref.")
@reports(RunError, api.ApiError)
def do_discard(runref, files, project):
    """Throw away a draft that will not be submitted.

    **`--files delete` by default, which is the opposite of `runs delete`**, and
    the difference is what the folder holds. A submitted run's folder holds
    generated media somebody paid for, so the default there keeps it. A draft's
    folder holds two payload documents and an empty `output/` — nothing was ever
    made — so keeping it by default would leave an orphan per abandoned idea.
    """
    record = resolve_run(runref, project)
    if record.get("status") != "draft":
        raise RunError(
            f"run {record['id']} is {record.get('status')} and has been "
            f"submitted; use `studio runs delete` if you mean to remove it")
    entities.delete_run(record["id"], files=files)
    print(f"discarded draft {record['id']} (files: {files})")


def _render_plan(record: dict) -> str:
    """A draft's payload, as the two documents hard rule #2 asks for.

    Rebuilt from the record rather than re-rendered from a live payload, because
    what a person is reading is what is STORED — a render assembled again from
    arguments would be a second opinion about the payload, and reading the
    second opinion while the first is what submits is precisely the gap this
    exists to close.
    """
    plan = record.get("plan") or {}
    sends = record.get("sends") or []
    lines = [
        "===== 1/2  PROMPT — serialized into the `prompt` string at submit time =====",
        json.dumps(plan.get("prompt"), indent=2, ensure_ascii=False),
        "",
        "===== 2/2  INPUT — the parameters this model receives =====",
        json.dumps({"run": record["id"], "model": record.get("model"),
                    "input": plan.get("params") or {}}, indent=2, ensure_ascii=False),
    ]
    if sends:
        lines += ["", "===== IMAGES — what this run sends, in order ====="]
        for n, send in enumerate(sends, 1):
            source = send.get("source") or {}
            where = source.get("kind", "?")
            if source.get("group"):
                where += f" · {source['group']}"
            if source.get("position"):
                where += f" · input {source['position']}"
            if source.get("output"):
                where += f" · output {source['output']}"
            lines.append(f"  {n}. [{send.get('role') or '?'}] "
                         f"{send.get('name') or send['node']}  ({where})")
    return "\n".join(lines)


@main.command("adopt")
@click.argument("project", required=True)
@click.option("--key", required=True,
              help="Node id of the existing object (or a name path to resolve).")
@reports(RunError, api.ApiError)
def do_adopt(project, key):
    """Wrap an existing artifact in a synthetic run.

    `--key` keeps its name — the flag is in `cli_surface_reference.json` and
    that file is a contract — but takes a node id now. A name path is still
    accepted and resolved, because a person reaching for this command is
    looking at a listing rather than at a row.
    """
    node_id = key if key.startswith("node-") else store.resolve(key)["id"]
    record = adopt(_project_id(project), node_id)
    print(json.dumps({k: record[k] for k in ("id", "status", "outputs")},
                     indent=2))


def _project_id(project: str) -> str:
    """A project name or id -> its id. `RunError` if there is no such one.

    An id passes through; a name is a listing and a match, because a name is a
    label that two projects may share and the API refuses to resolve one.
    """
    if project.startswith("proj-"):
        return project
    try:
        return P.by_name(entities.list_projects(), project, "project")["id"]
    except P.PathError as exc:
        raise RunError(f"{exc} (see `studio projects list`)") from exc
