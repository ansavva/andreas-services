"""`studio runs` — the run store, now an envelope in a row rather than three files.

A **run** is one submission to a model and everything about it. What changed is
where "everything about it" lives:

    the row   id, project, status, kind, engine, model, prediction id,
              timings, bindings (NODE IDS), characters, folder, outputs,
              lineage, cost, error                    — studio owns and validates
    the blobs request.json, prompt.json, result.json  — the provider owns, and
              studio stores them verbatim and never decodes them

That split is the entity model's fourth principle and it preserves the rule the
old module was built around. `PIPELINE.md` said "do not decode `request.json`",
and it was right for one reason — the pipeline changes the payload's shape
freely, so nothing should be invited to parse it. The rule survives, moved to
where it is actually true: the payload blobs. The envelope around them is
studio's own, so it can be queried.

WHAT THIS BUYS, CONCRETELY
--------------------------
`runs find --character` listed every project, listed every run in each, read
`request.json` for each and grepped. It is `GET /api/runs?character=…` — one
query. `runs list --model/--status/--since` did not exist at any price and is
three more parameters on the same query. Both are in `adapters/entities.py`, and
this module does not know how either is spelled.

BINDINGS ARE NODE IDS, AND THAT RETIRES A WHOLE MODULE
------------------------------------------------------
A binding used to be a path, checked here against four allowed roots. A path is
invalidated by any rename or move, which is why `domain/rewrite.py` existed and
why sixty-nine records once pointed at reference images that no longer existed.
A node id survives both by construction, so `rewrite.py` is deleted and the class
of bug with it.

**Hard rule #3 moved but did not weaken.** `check_bindings` still refuses a
URL-shaped binding here, before the request is sent, so `submit.py` can decline
to submit at all — and the API refuses it again, which is the strengthening: the
SPA goes through the API too, and it never went through this function.

ADDRESSING A RUN
----------------
    <project>/latest     the newest run there
    <project>/latest#2   its 2nd output (1-based); default is every output
    latest               when the project is supplied out of band (--project)
    run-<uuid>           the id, which is what a record holds

**A RUN HAS NO SLUG, AND THAT IS THE WHOLE OF ITS ADDRESSING.** It used to, and
the label was a worse copy of a column the row already had: every slug in
production read `<timestamp>_<hint>`, so it was unique only by embedding
`created` — which is what sorting reads, what `--since` filters on, and what a
timestamp in a folder name was imitating in the first place. Strip the timestamp
and 29 runs collapsed to 19 labels.

Nothing keyed on it and no claim row enforced it, so resolving one needed an
exact match, then a substring fallback, then an ambiguity error to prop it up.
All three are gone with it. A run is a machine event: it is found by `latest`,
by its id, or by the filters below — `--character`, `--model`, `--status`,
`--since` — which is how it was actually being found already.

A scene and a movie keep their slug and title. Those are things a person plans
and comes back to; a run is not.

CLI
---
    studio runs list <project> [--character|--model|--status|--since]
    studio runs find --character <name>
    studio runs show <project>/latest [--payload]
    studio runs outputs <project>/latest --presign
    studio runs delete <project>/latest [--files delete]
"""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

import click

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.errors import reports

SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
VID_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
#: What an id looks like. Not parsed for meaning — the prefix is for a human
#: reading a log, and nothing recovers anything from it.
ID_RE = re.compile(r"^(run|scene|movie|char|proj|node)-[0-9a-f-]{36}$")


class RunError(Exception):
    pass


def slugify(slug: str) -> str:
    """A run's human label. Still cleaned, because it becomes a folder name."""
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
    credentials and owns the TTL (`STUDIO_PRESIGN_TTL_SECONDS`). This used to
    take an `expires` it ignored, purely so the CLI's `--expires` had somewhere
    to go; that flag existed on eleven commands, could not be honoured by any of
    them, and is gone.
    """
    return [store.presign_node(node) for node in nodes]


# --- human review ---------------------------------------------------------

PROMPT_REF = "<< see document 1/2 — PROMPT >>"


def render_payload(run: str, model: str, endpoint: str, payload: dict,
                   bindings: dict | None = None) -> str:
    """Render a submission for approval as TWO JSON documents.

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
    sends: list[dict] | None = None,
) -> dict:
    """Create the run as a DRAFT. **Called before the submission AND before the
    approval.**

    The ordering is the reason `request.json` and `result.json` were two writes
    and is preserved as two calls: a prediction that times out still leaves a
    record, and a store that recorded nothing until success would lose exactly
    the runs worth investigating.

    `project` and each entry in `characters` are ids. Resolving a slug is the
    caller's job, done once, because a caller that has resolved a project
    usually needs the record for something else too.

    **No slug is sent.** A run has none; the API names its folder for its id.
    What the caller used to pass here as `slug` was doing two jobs, and only one
    of them was any good — see `--name` on `studio run`, which keeps the good
    one: what the output FILE is called.
    """
    clean = check_bindings(bindings or {})
    try:
        return entities.create_run(
            project=project, kind=kind, engine=engine, model=model,
            input=input, bindings=clean, plan=plan, sends=sends,
            characters=characters or [], prompt=prompt_source)
    except api.ApiError as exc:
        raise RunError(str(exc)) from exc


def upload_output(run_id: str, local: str, name: str | None = None) -> str:
    """Put one artifact in the run's `output/` and return its NODE ID.

    Three calls: the API mints the node and a presigned PUT together, the bytes
    go straight to S3, and `store.upload_to_url` confirms the node so the row
    records what landed. Deliberately not `store.write_into` — that would create
    a second node beside the one the route already made, and the run's `outputs`
    list would name the wrong one.

    **It was two calls until the confirm was added, and that is what made every
    `output/` folder look empty.** The bytes were always in S3 and the run page
    always drew them — it expands `outputs` by id and presigns off `blob_key`,
    which no listing does — so the only symptom was the folder. See
    `store.upload_to_url`.
    """
    base = name or os.path.basename(local)
    size = os.path.getsize(local)
    ct = mimetypes.guess_type(local)[0] or "application/octet-stream"
    signed = entities.add_run_output(run_id, base, size, ct)
    store.upload_to_url(signed, Path(local))
    return signed["node"]


def record_result(
    run_id: str, *, prediction_id: str | None, status: str,
    outputs: list[str] | None = None, source_urls: list[str] | None = None,
    error=None, extra: dict | None = None,
) -> dict:
    """Close the run: `PATCH` the envelope, and store the response verbatim.

    `outputs` are node ids and are already on the record — `upload_output` put
    them there. They are accepted here so a caller can keep the one call it
    always made, and they are not re-sent.

    The response document keeps the transient provider URLs, which is the one
    place they are allowed to survive: they are debugging material inside a blob
    nothing parses, not a binding anything replays.
    """
    entities.put_run_response(run_id, dumps({
        "prediction_id": prediction_id, "status": status,
        "completed_at": _now(), "outputs": outputs or [],
        "source_urls": source_urls or [], "error": _stringify(error),
        **(extra or {}),
    }))
    return entities.patch_run(run_id, status=status, prediction_id=prediction_id,
                              completed=_now(),
                              error=_stringify(error) if error is not None else None)


def _stringify(error):
    """An error as something JSON can hold.

    Exceptions arrive here from three call sites in `submit.py` and one in
    `board.py`, and `json.dumps` refuses them — which turned a failed prediction
    into a `TypeError` on the way to recording that it failed.
    """
    if error is None or isinstance(error, (str, int, float, bool, list, dict)):
        return error
    return str(error)


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

    **Order is the record's, not a listing's**, and that is a real change. It
    used to be a natural sort over `output/`'s children because the folder was
    the only source — which meant `-10` sorting before `-2` would hand a later
    run the wrong frame under the right name. The row holds the order the
    outputs were written in, so there is nothing left to re-derive.
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

def parse_runref(ref: str, default_project: str | None = None) -> tuple[str, str, int | None]:
    """'<project>/latest#2' -> ('<project>', 'latest', 2). Index 1-based, None = all."""
    if not ref:
        raise RunError("empty runref")
    body, _, idx = ref.partition("#")
    index = None
    if idx:
        if not idx.isdigit() or int(idx) < 1:
            raise RunError(f"runref index must be a positive integer: {ref!r}")
        index = int(idx)
    if "/" in body:
        project, _, run_ref = body.partition("/")
    else:
        project, run_ref = default_project, body
    if not project and not run_ref.startswith("run-"):
        raise RunError(
            f"runref {ref!r} has no project and none was supplied "
            "(use <project>/latest, a run id, or pass --project)"
        )
    return project, run_ref, index


def resolve_run(ref: str, default_project: str | None = None) -> dict:
    """A runref -> the run record.

    Returns the **record**, not a `(project, id)` pair. Every caller went
    straight on to read the run, and returning a pair meant a second round trip
    plus two more strings to keep in step.

    An id resolves directly and needs no project, which is what makes a record
    that stored a run id self-sufficient — the property the whole entity model
    is for.
    """
    project, run_ref, _index = parse_runref(ref, default_project)
    if run_ref.startswith("run-"):
        try:
            return entities.get_run(run_ref)
        except api.NotFound as exc:
            raise RunError(f"no run {run_ref}") from exc

    found = list_runs(_address(project))
    if not found:
        raise RunError(f"no runs in project {project!r}")
    if run_ref in ("latest", "last"):
        return entities.get_run(found[0]["id"])
    raise RunError(
        f"{run_ref!r} is not a runref. A run has no name to address it by — "
        f"use 'latest', or its id.\n"
        + "".join(f"       {r['id']}  {r['created'][:19]}  {r.get('model','')}\n"
                  for r in found[:5])
        + (f"       … and {len(found) - 5} more\n" if len(found) > 5 else "")
        + "       studio runs list <project> for the rest.")


def _address(project: str) -> str:
    """A project id passed through; anything else read as a slug a person typed."""
    return project if project.startswith("proj-") else entities.address(project)


def resolve_output_nodes(ref: str, default_project: str | None = None,
                         kinds: set[str] | None = None) -> list[str]:
    """The NODE IDS of a runref's output — what chaining consumes.

    Node ids, where this returned paths. That is the whole of #420: a later run
    binds these, and a binding that named a path would be stranded by any
    rename of the file it named.
    """
    _project, _run_ref, index = parse_runref(ref, default_project)
    record = resolve_run(ref, default_project)
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

    A run record read back from the API keys it `id`; documents written before
    #420 key it `node`. Reading only `node` made every runref binding
    (`--ref-run`, `--image-run`, `--start-run`, `--end-run`, and `add-refs
    --from-run`) die on `KeyError` against a live record. `engine/turnaround.py`
    already carries the same two-spelling read for the same reason.
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

    It used to render `record['slug']`, which no listing row has ever held — the
    projection is `{lib, id, created, status, model, kind, thumb}` — so
    `runs list` raised `KeyError` against the real API while passing against a
    test fake that projected off the full record. Reading with `.get` where a
    field is optional, and reading nothing that is not projected, is the rule
    here.
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
        character=entities.address(character) if character else None,
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

    **One API query**, where this listed every project, listed every run in each
    and read three documents per run to grep for a name. `--project` is now a
    filter applied to that query rather than the loop it used to drive.
    """
    address = entities.address(character)
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
    """`--presign` reaches `store` directly, and that is a fix.

    The flag is named `presign` and so is this module's function, so inside this
    body the flag shadows it — `presign(keys, expires)` called `True` and raised
    `TypeError: 'bool' object is not callable` for as long as the option
    existed. `--help` printed happily and nothing invoked it. Renaming the
    parameter is not available: `cli_surface_reference.json` records the dest,
    and it is a contract. Doing the work inline is. (The shadowing is harmless
    now that `presign` takes one argument, but the inline call stays: it is the
    thing that made the bug impossible rather than merely unlikely.)
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


@main.command("approve")
@click.argument("runref", required=True)
@click.option("--project", help="Default project for a bare runref.")
@reports(RunError, api.ApiError)
def do_approve(runref, project):
    """Read a draft's payload in full, then say yes to **that** payload.

    **No `--yes`, and there will not be one.** A person reads what is printed and
    answers, or nothing is approved: an approval flag is the door an agent walks
    through while believing some earlier exchange counted as approval. That
    sentence is already in `board.py` and `turnaround.py`; it matters more here,
    because what this writes is a durable record that somebody said yes.

    The digest is what turns that record into an approval rather than a
    timestamp. It names the exact words and the exact ordered images, so
    re-wording a prompt afterwards does not leave a stale yes behind — the API
    refuses the submission and says the payload moved.
    """
    record = resolve_run(runref, project)
    if record.get("status") != "draft":
        raise RunError(f"run {record['id']} is {record.get('status')}, not a draft")

    print(_render_plan(record))
    if not click.confirm(f"\napprove this payload for run {record['id']}?",
                         default=False):
        print("not approved.", file=sys.stderr)
        raise SystemExit(1)

    updated = entities.approve_run(record["id"], record["plan_digest"])
    print(f"approved {updated['id']} — submit it with: "
          f"studio runs submit {updated['id']}")


@main.command("submit")
@click.argument("runref", required=True)
@click.option("--project", help="Default project for a bare runref.")
@reports(RunError, api.ApiError)
def do_submit(runref, project):
    """Send an approved draft to the model. **This is what bills.**

    Deliberately not the same command as `approve`: the two exist apart so that
    the payload can be read in one place — a terminal, or the app — and sent from
    another, which is the whole point of the approval being a record rather than
    a keystroke.
    """
    record = resolve_run(runref, project)
    if record.get("status") != "approved":
        raise RunError(
            f"run {record['id']} is {record.get('status')}, not approved.\n"
            f"       studio runs approve {record['id']}")
    print(f"submitting {record['id']} …", file=sys.stderr)
    # The engine owns the submit lifecycle; importing it here rather than at the
    # top keeps `domain` free of `engine` at import time, which is the direction
    # the dependency arrow points everywhere else in this package.
    from studio_pipeline.engine import resubmit
    print(json.dumps(resubmit.submit_draft(record), indent=2))


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
    if record.get("status") not in ("draft", "approved"):
        raise RunError(
            f"run {record['id']} is {record.get('status')} and has been "
            f"submitted; use `studio runs delete` if you mean to remove it")
    entities.delete_run(record["id"], files=files)
    print(f"discarded draft {record['id']} (files: {files})")


def _render_plan(record: dict) -> str:
    """A draft's payload, as the two documents hard rule #2 asks for.

    Rebuilt from the record rather than re-rendered from a live payload, because
    what a person is approving is what is STORED — a render assembled again from
    arguments would be a second opinion about the payload, and approving the
    second opinion while the first is what submits is precisely the gap the
    digest exists to close.
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
    """A project slug or id -> its id. One call; `RunError` if there is no such one."""
    if project.startswith("proj-"):
        return project
    try:
        return entities.resolve_project(project)["id"]
    except api.NotFound as exc:
        raise RunError(f"no project {project!r} (see `studio projects list`)") from exc
