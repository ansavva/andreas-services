"""`studio runs` — the shared run store for every studio-* engine, plus its CLI.

A **run** is one submission to Replicate and everything about it, kept together
under the PROJECT it belongs to:

    projects/<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/
        request.json    what we sent   (references stored as S3 KEYS)
        prompt.json     the studio-media-prompt structured source, when one was used
        result.json     what came back (prediction id, status, output keys)
        output/         the artifact(s) — .mp4, .jpg, .png, however many

The run OWNS its output. Medium is an attribute (`result.json`, and the file
extension), never a folder name — the same shape holds whether Replicate
returned one video or ten images.

A run belongs to a **project**, not to a character. One piece of work can use
several characters, and a project can outlive any of them, so `request.json`
records both: `project` says where the run lives, `characters[]` says whose
likeness went into it. That list is what makes "every run using this character"
answerable now that the folder no longer says.

THE INVARIANT
-------------
The store is the only origin. Replicate never receives bytes — only a
short-lived presigned URL the API mints. Consequently `request.json` stores
**paths**, never presigned URLs: URLs expire (the record would rot), they are
~2 KB of noise each, and they carry time-limited access that must not outlive
the request. `record_request()` REFUSES to write a binding that looks like a
URL, so the rule is enforced in code rather than remembered.

Because paths are stable, any run replays: re-mint fresh URLs from the recorded
paths and resubmit.

WHERE THE WRITES GO, SINCE #304
-------------------------------
Through the API, and nothing here holds a bucket name or a credential.

A run is CREATED by `POST /api/runs` — one request that makes the run folder and
writes its documents together, and answers **409** if that folder is already
there. That refusal is worth having: a run id is `<timestamp>_<slug>`, so a
collision means the CLI re-sent a run rather than made a new one.

Everything after that is an ordinary write into a folder that now exists —
`result.json` through `store.write`, each output through `store.upload`. The
split is not tidiness: `request.json` is written BEFORE the submission and
`result.json` only after it comes back, which is what leaves a record behind
when a prediction times out. One call cannot do both, and a run that recorded
nothing until it succeeded would lose exactly the runs worth investigating.

**Documents are written as `text/plain`, not `application/json`.** The API's
run route decided that (see `_write_document` in `routes/nodes.py`): the
pipeline owns the shape of these documents and changes it freely, so nothing
should be invited to parse them. `write_json` here matches it deliberately —
otherwise a run's `request.json` and its `result.json` would carry different
content types depending only on which code path wrote them.

CHAINING
--------
Every artifact has a stable key inside its run, so a run can consume an earlier
run's output — as a start frame or as reference material — and record that
lineage. Runs are addressed by **runref**:

    <project>/<run_id>   <project>/2026-01-31_09-15-00_<slug>
    <project>/latest     the newest run in that project
    <run_id>             when the project is supplied out of band (--project)
    <runref>#2           pick the 2nd output (1-based); default is every output

CLI
---
    studio runs list <project> [--character <name>]
    studio runs show <project>/latest
    studio runs outputs <project>/latest --presign
    studio runs find --character <name>          # across every project
"""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
from pathlib import Path

import click

from studio_pipeline.adapters import api, store
from studio_pipeline.domain import (
    paths as P,
)
from studio_pipeline.errors import reports

RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[A-Za-z0-9._-]+$")
SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
# What a binding is allowed to point at. Anything else is a typo or a URL, and
# either way it must not reach a stored record.
#
# Plain paths since #303: there is no bucket prefix to apply, so these are the
# four roots of the tree as `paths.py` builds them.
KEY_ROOTS = (P.CHARACTERS + "/", P.PROJECTS + "/", "phrasebook/", P.config_root())
VID_EXTS = {".mp4", ".mov", ".webm", ".m4v"}


class RunError(Exception):
    pass


# --- naming ---------------------------------------------------------------

def slugify(slug: str) -> str:
    out = SLUG_RE.sub("-", (slug or "run").strip()).strip("-.")
    return out[:60] or "run"


def new_run_id(slug: str, when: dt.datetime | None = None) -> str:
    """A run id sorts lexically == chronologically: YYYY-MM-DD_HH-MM-SS_<slug>."""
    ts = (when or dt.datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    return f"{ts}_{slugify(slug)}"


def run_prefix(project: str, run_id: str) -> str:
    """Tree-relative — feeds `list_keys`. Use `run_key` for get/put."""
    return P.run_prefix(project, run_id)


def run_key(project: str, run_id: str, *parts: str) -> str:
    return P.run_key(project, run_id, *parts)


# --- json io --------------------------------------------------------------

#: The content type every run document is stored under. See the module
#: docstring — the API's run route picks this, and the two write paths must not
#: disagree about it.
DOCUMENT_TYPE = "text/plain; charset=utf-8"


def dumps(obj) -> str:
    """The one serialization for every run document.

    `sort_keys=False` is load-bearing rather than a default spelled out: these
    documents are read by people, and `run_id` first then `project` then what
    was sent is the order they are written in.
    """
    return json.dumps(obj, indent=2, sort_keys=False)


def write_json(path: str, obj) -> str:
    """Write one document into a folder that already exists.

    Not a creation path. `store.write` resolves the parent, so this can only
    write into a run `POST /api/runs` has already made — which is the ordering
    the run store has always had, now enforced rather than implied.
    """
    store.write(path, dumps(obj).encode(), content_type=DOCUMENT_TYPE)
    return path


def read_json(path: str):
    """One document, or None when it is not there.

    None rather than a raise, unchanged from the boto3 version: `run_record`
    asks for all three documents and a run legitimately has no `result.json`
    until it finishes, and `prompt.json` only when a structured source was used.
    """
    try:
        return json.loads(store.read(path).decode())
    except api.NotFound:
        return None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# --- the invariant --------------------------------------------------------

def check_bindings(bindings: dict) -> dict:
    """Bindings map an input field -> the S3 key(s) bound to it. Keys ONLY.

    Refuses anything URL-shaped: a presigned URL in a stored record is expired
    data plus leaked time-limited access. This is the enforcement point for
    'we never upload assets to Replicate and never store the signed URLs'.
    """
    clean: dict = {}
    for field, val in (bindings or {}).items():
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            if not isinstance(v, str):
                raise RunError(f"binding {field!r} must be S3 key string(s), got {type(v).__name__}")
            if "://" in v or v.startswith("//"):
                raise RunError(
                    f"binding {field!r} looks like a URL, not an S3 key: {v[:60]}…\n"
                    "Store keys; presigned URLs are minted fresh at submit time."
                )
            if not v.startswith(KEY_ROOTS):
                raise RunError(
                    f"binding {field!r} is not a key in this bucket: {v!r}\n"
                    f"Expected one of {list(KEY_ROOTS)} — build keys with paths.py."
                )
        clean[field] = vals if isinstance(val, list) else val
    return clean


def presign(paths: list[str], expires: int = 3600) -> list[str]:
    """Mint fresh presigned URLs — the ONLY way assets reach Replicate.

    `expires` is accepted and ignored. The API signs these against its own
    credentials and owns the TTL (`STUDIO_PRESIGN_TTL_SECONDS`), so a number
    passed here cannot be honoured. The parameter survives because `submit.py`
    threads `--expires` down from a CLI flag that
    `cli_surface_reference.json` records, and #308 keeps this epic's diff to
    that file to the three session commands. `objects/presign.py` warns when a
    person typed one; this is the library path and has no context to warn from.
    """
    return [store.presign(path) for path in paths]


# --- human review ---------------------------------------------------------

PROMPT_REF = "<< see document 1/2 — PROMPT >>"


def render_payload(run: str, model: str, endpoint: str, payload: dict,
                   bindings: dict | None = None) -> str:
    """Render a submission for approval as TWO JSON documents.

    One combined document is unreviewable: `prompt` is itself a serialized JSON
    object (studio-media-prompt authors it that way), so nesting it inside the payload
    double-escapes it onto one enormous line. Splitting them keeps both as real,
    indented JSON — the prompt as the structured object it actually is, and the
    payload as the parameters the model receives. This mirrors how a run is
    stored: prompt.json beside request.json.
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

def characters_used(bindings: dict | None, declared: list[str] | None = None) -> list[str]:
    """Which characters a run used: what was declared, plus what the keys reveal.

    Inferring from the bindings means the list cannot silently disagree with the
    images actually sent — a `--character` that contributed nothing is still
    recorded (it was asked for), but an image nobody declared is caught.
    """
    found = set(declared or [])
    for val in (bindings or {}).values():
        for v in (val if isinstance(val, list) else [val]):
            if isinstance(v, str) and (c := P.character_of(v)):
                found.add(c)
    return sorted(found)


def record_request(
    project: str, run_id: str, *, kind: str, engine: str, model: str,
    input: dict, bindings: dict | None = None, prompt_source: dict | None = None,
    characters: list[str] | None = None, extra: dict | None = None,
) -> str:
    """Create the run and write request.json (and prompt.json, when there is one).

    **This is the call that brings the run into existence** — `POST /api/runs`
    makes the folder and writes both documents in one request. Everything later
    in the run's life writes into that folder and would fail without it, which
    is why nothing else creates it.

    The bindings are checked BEFORE the request is sent, not by the API. It
    stores these documents as bytes and never decodes them, so the only place
    hard rule #3 can be enforced is here — and `submit.py` catches the
    `RunError` and refuses to submit at all.
    """
    clean = check_bindings(bindings or {})
    doc = {
        "run_id": run_id,
        "project": project,
        "characters": characters_used(clean, characters),
        "kind": kind,                 # "image" | "video" | …
        "engine": engine,             # which studio-* skill submitted it
        "model": model,               # "google/nano-banana-pro"
        "created_at": _now(),
        "input": input,               # payload MINUS the URL-bearing fields
        "bindings": clean,
        **(extra or {}),
    }
    documents = {"request.json": dumps(doc)}
    if prompt_source is not None:
        documents["prompt.json"] = dumps(prompt_source)

    try:
        api.post("/api/runs", {
            "parent": store.folder(P.runs_prefix(project))["id"],
            "name": run_id,
            "documents": documents,
        })
    except api.Conflict as exc:
        # A run id carries a timestamp to the second, so this is not two runs
        # racing — it is the same run recorded twice.
        raise RunError(f"run {project}/{run_id} is already recorded") from exc
    return run_key(project, run_id, "request.json")


def upload_output(project: str, run_id: str, local: str, name: str | None = None) -> str:
    """Put one artifact in the run's `output/` folder and return its path.

    The folder is ensured here rather than at `record_request`, so a run that
    failed or timed out leaves no empty `output/` behind. Under S3 that folder
    only ever appeared when an object landed in it; this keeps that true now
    that it is a row.

    Deliberately NOT `POST /api/runs`'s `outputs` field, which would put the
    artifacts flat in the run folder — a name is one segment, so that route
    cannot nest them. `<run>/output/<file>` is the layout `run_outputs`,
    `resolve_output_keys`, every scene and movie manifest and every `SKILL.md`
    are written in terms of, and it is not what #304 is here to change.
    """
    base = name or os.path.basename(local)
    path = run_key(project, run_id, "output", base)
    store.folder(run_key(project, run_id, "output"))
    ct = mimetypes.guess_type(local)[0] or "application/octet-stream"
    store.upload(path, Path(local), content_type=ct)
    return path


def record_result(
    project: str, run_id: str, *, prediction_id: str | None, status: str,
    outputs: list[str] | None = None, source_urls: list[str] | None = None,
    error=None, extra: dict | None = None,
) -> str:
    outputs = outputs or []
    media_types = sorted({mimetypes.guess_type(k)[0] or "application/octet-stream" for k in outputs})
    doc = {
        "run_id": run_id,
        "project": project,
        "prediction_id": prediction_id,
        "status": status,
        "completed_at": _now(),
        "media_types": media_types,
        "outputs": outputs,            # S3 keys inside this run
        "source_urls": source_urls or [],   # transient Replicate URLs, for debugging
        "error": error,
        **(extra or {}),
    }
    return write_json(run_key(project, run_id, "result.json"), doc)


# --- reading runs ---------------------------------------------------------

def list_runs(project: str) -> list[str]:
    """Run ids in a project, oldest first (ids sort chronologically)."""
    return P.list_ids(P.runs_prefix(project))


def run_outputs(project: str, run_id: str) -> list[str]:
    """Output paths of a run, natural-sorted.

    **The sort is not cosmetic.** These paths become `[Image1]..[ImageN]` when
    a later run consumes them, and the mapping is positional — the API returns
    children name-ascending, which is lexical, so `-10` would arrive before
    `-2` and a model would be handed the wrong frame under the right name.

    A run with no `output/` folder is an empty list rather than an error: a run
    that failed, timed out or is still in flight legitimately has none, and
    every caller here already distinguishes empty from broken by the status in
    `result.json`.
    """
    folder = run_key(project, run_id, "output")
    try:
        entries = store.children(folder)
    except api.NotFound:
        return []
    names = sorted(
        (e["name"] for e in entries if e.get("kind") == "file" and e.get("name")),
        key=store.natural_key,
    )
    return [f"{folder}/{name}" for name in names]


def run_record(project: str, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "project": project,
        "request": read_json(run_key(project, run_id, "request.json")),
        "result": read_json(run_key(project, run_id, "result.json")),
        "prompt": read_json(run_key(project, run_id, "prompt.json")),
        "outputs": run_outputs(project, run_id),
    }


def run_characters(project: str, run_id: str) -> list[str]:
    """The characters a run recorded. Falls back to reading its bindings."""
    req = read_json(run_key(project, run_id, "request.json")) or {}
    if "characters" in req:
        return req["characters"]
    return characters_used(req.get("bindings"))


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
        project, _, run_id = body.partition("/")
    else:
        project, run_id = default_project, body
    if not project:
        raise RunError(
            f"runref {ref!r} has no project and none was supplied "
            "(use <project>/<run_id> or pass --project)"
        )
    return project, run_id, index


def resolve_run(ref: str, default_project: str | None = None) -> tuple[str, str]:
    project, run_id, _ = parse_runref(ref, default_project)
    if run_id in ("latest", "last"):
        runs = list_runs(project)
        if not runs:
            raise RunError(f"no runs in project {project!r}")
        return project, runs[-1]
    if not RUN_ID_RE.match(run_id):
        # Allow a unique suffix match, e.g. '<slug>'
        matches = [r for r in list_runs(project) if r.endswith(run_id) or run_id in r]
        if len(matches) == 1:
            return project, matches[0]
        if not matches:
            raise RunError(f"no run matching {run_id!r} in project {project!r}")
        raise RunError(f"runref {run_id!r} is ambiguous in {project!r}: {matches[-5:]}")
    return project, run_id


def resolve_output_keys(ref: str, default_project: str | None = None,
                        kinds: set[str] | None = None) -> list[str]:
    """Paths of a runref's output — what chaining consumes."""
    _project, _run_id, index = parse_runref(ref, default_project)
    project, run_id = resolve_run(ref, default_project)
    keys = run_outputs(project, run_id)
    if kinds:
        keys = [k for k in keys if os.path.splitext(k)[1].lower() in kinds]
    if not keys:
        have = [os.path.splitext(k)[1] for k in run_outputs(project, run_id)]
        raise RunError(
            f"run {project}/{run_id} has no output matching {sorted(kinds or [])} "
            f"(it holds {have or 'nothing'})"
        )
    if index is not None:
        if index > len(keys):
            raise RunError(f"run {project}/{run_id} has {len(keys)} output(s); asked for #{index}")
        return [keys[index - 1]]
    return keys


# --- searching across projects --------------------------------------------

def find_by_character(character: str, projects: list[str] | None = None) -> list[str]:
    """Every runref that recorded this character, across every project.

    Runs used to live in a character's folder, so this was a listing. They live
    in a project now, so it is a scan of what each run recorded about itself.
    """
    hits = []
    for project in (projects or P.list_projects()):
        for run_id in list_runs(project):
            if character in run_characters(project, run_id):
                hits.append(f"{project}/{run_id}")
    return hits


# --- legacy import --------------------------------------------------------

def adopt(project: str, key: str) -> str:
    """Wrap a pre-scheme artifact in a synthetic run so history is uniform.

    Existing files are already named <YYYY-MM-DD_HH-MM-SS>_<slug>.<ext>, so the
    run id is taken from the filename and nothing is renamed.

    **A move now, where it used to be a copy and a delete.** The catalog moves
    a node by rewriting one row, so the bytes never travel and — the part that
    matters — the node keeps its id. Anything that already named this file, a
    share link included, still names it after it has been adopted. The old
    `CopyObject`/`DeleteObject` pair could not offer that: it produced a
    different object and destroyed the original.

    The run is created before the move, so a failure leaves a run holding its
    `request.json` and no output — visible, and re-runnable once the cause is
    fixed. The other order would leave the artifact parented to a folder that
    was never made.
    """
    base = os.path.basename(key)
    stem, ext = os.path.splitext(base)
    run_id = stem if RUN_ID_RE.match(stem) else new_run_id(stem)
    dst = run_key(project, run_id, "output", base)
    if dst == key.strip("/"):
        raise RunError(f"{key} is already inside its run")
    try:
        node = store.resolve(key)
    except api.NotFound as exc:
        raise RunError(f"no such object: {key}") from exc

    record_request(project, run_id, kind="video" if ext.lower() in VID_EXTS else "image",
                   engine="(pre-scheme)", model="(unrecorded)", input={},
                   bindings={})
    output = store.folder(run_key(project, run_id, "output"))
    api.patch(f"/api/nodes/{node['id']}", {"parent": output["id"]})
    record_result(project, run_id, prediction_id=None, status="adopted",
                  outputs=[dst], extra={"note": "imported from the legacy output/ folder; "
                                                "prompt and model were not recorded at the time"})
    return dst


# --- CLI ------------------------------------------------------------------

@click.group(help=__doc__)
def main():
    pass


def _warn_ignored_expiry(expires: int) -> None:
    """`--expires` is accepted and ignored, loudly. See `objects/presign.py`.

    The API signs these URLs against its own credentials and owns their TTL, so
    a number typed here cannot be honoured. The flag stays because
    `cli_surface_reference.json` is a contract; saying nothing would make it the
    silent no-op the `XHARNESS_S3_*` rename exists to have avoided.
    """
    context = click.get_current_context(silent=True)
    if context is None:
        return
    source = context.get_parameter_source("expires")
    if source is not None and source.name != "DEFAULT":
        click.echo(
            f"warning: --expires {expires} is ignored; the API sets the URL's lifetime.",
            err=True,
        )










@main.command("list")
@click.argument("project", required=True)
@click.option("--character", help="Only runs that recorded this character.")
@click.option("--json", "json_", is_flag=True)
@reports(RunError)
def do_list(project, character, json_):
    runs = list_runs(project)
    if character:
        runs = [r for r in runs
                if character in run_characters(project, r)]
    if json_:
        print(json.dumps(runs, indent=2))
    else:
        print("\n".join(runs) or f"(no runs in {project})")


@main.command("find")
@click.option("--character", required=True)
@click.option("--json", "json_", is_flag=True)
@click.option("--project", multiple=True, help="Limit to these projects. Repeatable.")
@reports(RunError)
def do_find(character, json_, project):
    hits = find_by_character(character, project)
    if json_:
        print(json.dumps(hits, indent=2))
    else:
        print("\n".join(hits) or f"(no runs recorded {character})")


@main.command("show")
@click.argument("runref", required=True)
@click.option("--project", help="Default project for a bare run id.")
@reports(RunError)
def do_show(runref, project):
    project, run_id = resolve_run(runref, project)
    print(json.dumps(run_record(project, run_id), indent=2))


@main.command("outputs")
@click.argument("runref", required=True)
@click.option("--expires", type=int, default=3600)
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
@click.option("--project", help="Default project for a bare run id.")
@reports(RunError)
def do_outputs(runref, expires, json_, presign, project):
    """`--presign` reaches `store` directly, and that is a fix.

    The flag is named `presign` and so is this module's function, so inside
    this body the flag shadows it — `presign(s3, keys, expires)` called `True`
    and raised `TypeError: 'bool' object is not callable` for as long as the
    option has existed. `--help` printed happily, and nothing invoked it.
    Renaming the parameter is not available: `cli_surface_reference.json`
    records the dest, and it is a contract. Doing the work inline is.
    """
    _warn_ignored_expiry(expires)
    keys = resolve_output_keys(runref, project)
    vals = [store.presign(key) for key in keys] if presign else keys
    print(json.dumps(vals, indent=2) if json_ else "\n".join(vals))


@main.command("adopt")
@click.argument("project", required=True)
@click.option("--key", required=True, help="Full S3 key of the existing object.")
@reports(RunError)
def do_adopt(project, key):
    print(adopt(project, key))

