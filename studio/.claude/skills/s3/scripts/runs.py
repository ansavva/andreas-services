# /// script
# requires-python = ">=3.13"
# dependencies = ["boto3"]
# ///
"""runs.py — the shared run store for every studio-* engine, plus its CLI.

A **run** is one submission to Replicate and everything about it, kept together
under the PROJECT it belongs to:

    projects/<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/
        request.json    what we sent   (references stored as S3 KEYS)
        prompt.json     the studio-prompt structured source, when one was used
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
S3 is the only origin. Replicate never receives bytes — only a short-lived
presigned URL pointing back into this bucket. Consequently `request.json` stores
S3 **keys**, never presigned URLs: URLs expire (the record would rot), they are
~2 KB of noise each, and they carry time-limited bucket access that must not
outlive the request. `record_request()` REFUSES to write a binding that looks
like a URL, so the rule is enforced in code rather than remembered.

Because keys are stable, any run replays: re-mint fresh URLs from the recorded
keys and resubmit.

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
    uv run runs.py list <project> [--character <name>]
    uv run runs.py show <project>/latest
    uv run runs.py outputs <project>/latest --presign
    uv run runs.py find --character <name>          # across every project
    uv run runs.py favorite <project>/latest#1      # keep a take
    uv run runs.py favorites <project>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P  # noqa: E402  — the one module that knows the bucket's shape
import s3_common as s3c  # noqa: E402

RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[A-Za-z0-9._-]+$")
SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
# What a binding is allowed to point at. Anything else is a typo or a URL, and
# either way it must not reach a stored record.
KEY_ROOTS = (s3c.key(P.CHARACTERS + "/"), s3c.key(P.PROJECTS + "/"), s3c.key("phrasebook/"))
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

def write_json(s3, key: str, obj) -> str:
    s3.put_object(
        Bucket=s3c.BUCKET,
        Key=key,
        Body=json.dumps(obj, indent=2, sort_keys=False).encode(),
        ContentType="application/json",
    )
    return key


def read_json(s3, key: str):
    try:
        return json.loads(s3.get_object(Bucket=s3c.BUCKET, Key=key)["Body"].read().decode())
    except s3.exceptions.NoSuchKey:
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


def presign(s3, keys: list[str], expires: int = 3600) -> list[str]:
    """Mint fresh presigned URLs for keys — the ONLY way assets reach Replicate."""
    return [
        s3.generate_presigned_url(
            "get_object", Params={"Bucket": s3c.BUCKET, "Key": k}, ExpiresIn=expires
        )
        for k in keys
    ]


# --- human review ---------------------------------------------------------

PROMPT_REF = "<< see document 1/2 — PROMPT >>"


def render_payload(run: str, model: str, endpoint: str, payload: dict,
                   bindings: dict | None = None) -> str:
    """Render a submission for approval as TWO JSON documents.

    One combined document is unreviewable: `prompt` is itself a serialized JSON
    object (studio-prompt authors it that way), so nesting it inside the payload
    double-escapes it onto one enormous line. Splitting them keeps both as real,
    indented JSON — the prompt as the structured object it actually is, and the
    payload as the parameters the model receives. This mirrors how a run is
    stored: prompt.json beside request.json.
    """
    prompt = payload.get("prompt")
    try:  # studio-prompt emits a serialized JSON object — show it unpacked
        prompt_doc = json.loads(prompt) if isinstance(prompt, str) else prompt
    except json.JSONDecodeError:
        prompt_doc = prompt  # plain prose prompt; show as-is

    inp = {k: v for k, v in payload.items() if k != "prompt"}
    if prompt is not None:
        inp["prompt"] = PROMPT_REF
    for field, val in (bindings or {}).items():
        inp[field] = ([f"<presigned: {k}>" for k in val] if isinstance(val, list)
                      else f"<presigned: {val}>")

    dump = lambda o: json.dumps(o, indent=2, ensure_ascii=False)  # noqa: E731
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
    s3, project: str, run_id: str, *, kind: str, engine: str, model: str,
    input: dict, bindings: dict | None = None, prompt_source: dict | None = None,
    characters: list[str] | None = None, extra: dict | None = None,
) -> str:
    """Write request.json (and prompt.json when a structured source was used)."""
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
    key = write_json(s3, run_key(project, run_id, "request.json"), doc)
    if prompt_source is not None:
        write_json(s3, run_key(project, run_id, "prompt.json"), prompt_source)
    return key


def upload_output(s3, project: str, run_id: str, local: str, name: str | None = None) -> str:
    base = name or os.path.basename(local)
    key = run_key(project, run_id, "output", base)
    ct = mimetypes.guess_type(local)[0] or "application/octet-stream"
    s3.upload_file(local, s3c.BUCKET, key, ExtraArgs={"ContentType": ct})
    return key


def record_result(
    s3, project: str, run_id: str, *, prediction_id: str | None, status: str,
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
    return write_json(s3, run_key(project, run_id, "result.json"), doc)


# --- reading runs ---------------------------------------------------------

def list_runs(s3, project: str) -> list[str]:
    """Run ids in a project, oldest first (ids sort chronologically)."""
    return P.list_ids(s3, P.runs_prefix(project))


def run_outputs(s3, project: str, run_id: str) -> list[str]:
    """Output keys of a run, natural-sorted."""
    return s3c.list_keys(s3, f"{run_prefix(project, run_id)}/output")


def run_record(s3, project: str, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "project": project,
        "request": read_json(s3, run_key(project, run_id, "request.json")),
        "result": read_json(s3, run_key(project, run_id, "result.json")),
        "prompt": read_json(s3, run_key(project, run_id, "prompt.json")),
        "outputs": run_outputs(s3, project, run_id),
    }


def run_characters(s3, project: str, run_id: str) -> list[str]:
    """The characters a run recorded. Falls back to reading its bindings."""
    req = read_json(s3, run_key(project, run_id, "request.json")) or {}
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


def resolve_run(s3, ref: str, default_project: str | None = None) -> tuple[str, str]:
    project, run_id, _ = parse_runref(ref, default_project)
    if run_id in ("latest", "last"):
        runs = list_runs(s3, project)
        if not runs:
            raise RunError(f"no runs in project {project!r}")
        return project, runs[-1]
    if not RUN_ID_RE.match(run_id):
        # Allow a unique suffix match, e.g. '<slug>'
        matches = [r for r in list_runs(s3, project) if r.endswith(run_id) or run_id in r]
        if len(matches) == 1:
            return project, matches[0]
        if not matches:
            raise RunError(f"no run matching {run_id!r} in project {project!r}")
        raise RunError(f"runref {run_id!r} is ambiguous in {project!r}: {matches[-5:]}")
    return project, run_id


def resolve_output_keys(s3, ref: str, default_project: str | None = None,
                        kinds: set[str] | None = None) -> list[str]:
    """S3 keys of a runref's output — what chaining consumes."""
    _project, _run_id, index = parse_runref(ref, default_project)
    project, run_id = resolve_run(s3, ref, default_project)
    keys = run_outputs(s3, project, run_id)
    if kinds:
        keys = [k for k in keys if os.path.splitext(k)[1].lower() in kinds]
    if not keys:
        have = [os.path.splitext(k)[1] for k in run_outputs(s3, project, run_id)]
        raise RunError(
            f"run {project}/{run_id} has no output matching {sorted(kinds or [])} "
            f"(it holds {have or 'nothing'})"
        )
    if index is not None:
        if index > len(keys):
            raise RunError(f"run {project}/{run_id} has {len(keys)} output(s); asked for #{index}")
        return [keys[index - 1]]
    return keys


# --- favorites ------------------------------------------------------------

def favorite(s3, ref: str, default_project: str | None = None) -> list[str]:
    """Copy a run output into the project's favorites/.

    `favorites/` existed as a folder with nothing that wrote to it, which is how
    it filled with unattributable files. Copying through here keeps the run as
    the history and the favorite as a pointer to a moment in it — the basename
    carries the run id, so a keeper is always traceable back.
    """
    project, run_id = resolve_run(s3, ref, default_project)
    keys = resolve_output_keys(s3, ref, default_project)
    out = []
    for k in keys:
        ext = os.path.splitext(k)[1]
        dst = P.favorite_key(project, f"{run_id}{ext}")
        s3.copy_object(Bucket=s3c.BUCKET, Key=dst,
                       CopySource={"Bucket": s3c.BUCKET, "Key": k},
                       MetadataDirective="COPY")
        out.append(dst)
    return out


def list_favorites(s3, project: str) -> list[str]:
    return s3c.list_keys(s3, P.favorites_prefix(project))


# --- searching across projects --------------------------------------------

def find_by_character(s3, character: str, projects: list[str] | None = None) -> list[str]:
    """Every runref that recorded this character, across every project.

    Runs used to live in a character's folder, so this was a listing. They live
    in a project now, so it is a scan of what each run recorded about itself.
    """
    hits = []
    for project in (projects or P.list_projects(s3)):
        for run_id in list_runs(s3, project):
            if character in run_characters(s3, project, run_id):
                hits.append(f"{project}/{run_id}")
    return hits


# --- legacy import --------------------------------------------------------

def adopt(s3, project: str, key: str) -> str:
    """Wrap a pre-scheme artifact in a synthetic run so history is uniform.

    Existing files are already named <YYYY-MM-DD_HH-MM-SS>_<slug>.<ext>, so the
    run id is taken from the filename and nothing is renamed.
    """
    base = os.path.basename(key)
    stem, ext = os.path.splitext(base)
    run_id = stem if RUN_ID_RE.match(stem) else new_run_id(stem)
    dst = run_key(project, run_id, "output", base)
    if dst == key:
        raise RunError(f"{key} is already inside its run")
    s3.copy_object(Bucket=s3c.BUCKET, CopySource={"Bucket": s3c.BUCKET, "Key": key},
                   Key=dst, MetadataDirective="COPY")
    s3.delete_object(Bucket=s3c.BUCKET, Key=key)
    record_request(s3, project, run_id, kind="video" if ext.lower() in VID_EXTS else "image",
                   engine="(pre-scheme)", model="(unrecorded)", input={},
                   bindings={})
    record_result(s3, project, run_id, prediction_id=None, status="adopted",
                  outputs=[dst], extra={"note": "imported from the legacy output/ folder; "
                                                "prompt and model were not recorded at the time"})
    return dst


# --- CLI ------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="List a project's runs, oldest first.")
    p.add_argument("project")
    p.add_argument("--character", help="Only runs that recorded this character.")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("find", help="Runs using a character, across every project.")
    p.add_argument("--character", required=True)
    p.add_argument("--project", action="append", help="Limit to these projects. Repeatable.")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("show", help="Print a run's full record.")
    p.add_argument("runref")
    p.add_argument("--project", help="Default project for a bare run id.")

    p = sub.add_parser("outputs", help="Print a runref's output keys (or presigned URLs).")
    p.add_argument("runref")
    p.add_argument("--project", help="Default project for a bare run id.")
    p.add_argument("--presign", action="store_true")
    p.add_argument("--expires", type=int, default=3600)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("favorite", help="Copy a run's output into the project's favorites/.")
    p.add_argument("runref")
    p.add_argument("--project", help="Default project for a bare run id.")

    p = sub.add_parser("favorites", help="List a project's favorites.")
    p.add_argument("project")

    p = sub.add_parser("adopt", help="Wrap a loose object in a synthetic run.")
    p.add_argument("project")
    p.add_argument("--key", required=True, help="Full S3 key of the existing object.")

    args = ap.parse_args()
    s3 = s3c.client()

    try:
        if args.cmd == "list":
            runs = list_runs(s3, args.project)
            if args.character:
                runs = [r for r in runs
                        if args.character in run_characters(s3, args.project, r)]
            if args.json:
                print(json.dumps(runs, indent=2))
            else:
                print("\n".join(runs) or f"(no runs in {args.project})")
        elif args.cmd == "find":
            hits = find_by_character(s3, args.character, args.project)
            if args.json:
                print(json.dumps(hits, indent=2))
            else:
                print("\n".join(hits) or f"(no runs recorded {args.character})")
        elif args.cmd == "show":
            project, run_id = resolve_run(s3, args.runref, args.project)
            print(json.dumps(run_record(s3, project, run_id), indent=2))
        elif args.cmd == "outputs":
            keys = resolve_output_keys(s3, args.runref, args.project)
            vals = presign(s3, keys, args.expires) if args.presign else keys
            print(json.dumps(vals, indent=2) if args.json else "\n".join(vals))
        elif args.cmd == "favorite":
            print("\n".join(favorite(s3, args.runref, args.project)))
        elif args.cmd == "favorites":
            keys = list_favorites(s3, args.project)
            print("\n".join(keys) or f"(no favorites in {args.project})")
        elif args.cmd == "adopt":
            print(adopt(s3, args.project, args.key))
    except RunError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
