"""`studio projects` — a PROJECT is the unit of production, and this manages them.

    projects/<project>/
        project.json    name, description, the characters involved
        runs/           append-only history (runs.py)
        chains/         a scene's own frames, in order (frames.py)
        scenes/         runs cut into one continuous take (scenes.py)
        movies/         scenes cut into one piece (movies.py)
        input/          the working pool — uploads and frames to drive from

PROJECT vs CHARACTER
--------------------
A character is an identity record; a project is a piece of work. They used to be
the same folder, which meant work involving two characters had nowhere to live
and work involving none had to borrow a fake character called `misc`. Now a
project names the characters it involves, and any run inside it records which
ones it actually used.

Nothing is inferred: every generating command takes an explicit `--project`.
Guessing where output lands is the one thing that cannot be undone by rerunning
a command, so the answer is always asked for rather than assumed.

THE INPUT POOL
--------------
`input/` is the project's working material — an upload to edit, a frame pulled
off a clip to drive the next one. It is uncapped and never sent "in full"; it is
picked from. That is the opposite of a character's `reference/`, which is
identity and is chosen from a described index (see studio-media-character).

Pool basenames are `<project>_in_<n>.<ext>`, numbered from the PROJECT — not
from a character. The first projects happen to be named after characters, so
those agreed by coincidence; deriving from the project is what keeps the next
project's pool correctly named.

WHERE THE WRITES GO, SINCE #305
-------------------------------
Through the API. Nothing here holds a bucket name or a credential.

**Creating a project now creates a folder, and that is not a formality.**
`project.json` used to be a bare `PutObject` at `projects/<p>/project.json` — S3
invented the folder from the slashes in the key. The catalog does not: a file
node needs a parent that exists, so `write_project` asks for
`projects/<p>` first. Without that step `projects new` would fail on a parent
nobody had made, and so would every run recorded into the project afterwards.

`project.json` keeps `application/json`, unlike a run's documents, which the
API's run route deliberately stores as `text/plain` so nothing is tempted to
parse them. The difference is real rather than an oversight: this file IS
parsed, by `read_project`, on every `projects show`.

CLI
---
    studio projects list
    studio projects new <project> --character <name> --description "…"
    studio projects show <project>
    studio projects add-inputs <project> file.png [file2.png …] [--json]
    studio projects inputs <project> [--json|--presign]
"""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
import sys

import click

from pathlib import Path

from studio_pipeline.errors import die
from studio_pipeline.adapters import api, store  # noqa: E402
from studio_pipeline.domain import paths as P  # noqa: E402

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
PROJECT_FILE = "project.json"




def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ── the record ──────────────────────────────────────────────────────────────

def read_project(project: str) -> dict | None:
    """The project record, or None when there is not one.

    **Only a 404 means "no record".** This used to swallow every exception,
    which made a permission failure and a missing file the same answer — so
    `projects show` on a library you are not a member of would have reported an
    uncreated project rather than a refusal. `store.read` raises `Forbidden`
    separately and it is left to surface.
    """
    try:
        return json.loads(store.read(P.project_json_key(project)).decode())
    except api.NotFound:
        return None


def write_project(doc: dict) -> str:
    """Write `project.json`, creating the project's folder if it is not there.

    **The folder is the new part.** S3 invented `projects/<p>/` out of the
    slashes in the key; the catalog needs a parent node to hang the file on, so
    this asks for one. `store.folder` makes any missing ancestor too, which is
    what lets the very first project in a fresh library be created at all —
    `projects/` does not exist either until something asks for it.

    The trailing newline is kept: these files are read in a terminal, and it is
    what every existing one in the tree already has.
    """
    path = P.project_json_key(doc["name"])
    store.folder(P.project_prefix(doc["name"]))
    store.write(path, (json.dumps(doc, indent=2) + "\n").encode(),
                content_type="application/json")
    return path


def require_project(project: str | None) -> str:
    """The one place a missing --project is turned into a usable error.

    It lists what exists, because the useful answer to "which project?" is the
    set of real options, not the name of the flag that was left out.
    """
    if not project:
        have = P.list_projects()
        die("no project given. Every generating command needs --project.\n"
            f"       existing projects: {', '.join(have) or '(none yet)'}\n"
            "       create one with: studio projects new <project>")
    P.check_slug(project, "project name")
    return project


# ── the input pool ──────────────────────────────────────────────────────────

def pool_max_index(project: str) -> int:
    """Highest N among `<project>_in_<n>.<ext>` already in the pool.

    Read off the names rather than counted: the pool is renumbered and pruned by
    hand, so `len()` would reuse an index the moment anything was removed and
    two different images would answer to one name.
    """
    pat = re.compile(rf"^{re.escape(project)}_in_(\d+)\.")
    hi = 0
    for entry in store.files(P.input_prefix(project)):
        if (m := pat.match(entry["name"])):
            hi = max(hi, int(m.group(1)))
    return hi


def add_inputs(project: str, paths: list[str]) -> list[dict]:
    """Upload local files into the pool, numbered on from what is there.

    The pool folder is ensured once, not per file — a project created before
    `input/` was ever written to has no such node, and the first upload is
    where that stops being true.
    """
    n = pool_max_index(project)
    added = []
    if paths:
        store.folder(P.input_prefix(project))
    for local in paths:
        if not os.path.isfile(local):
            die(f"not a file: {local}")
        ext = os.path.splitext(local)[1].lower()
        if ext not in IMG_EXTS:
            die(f"{local}: the input pool holds images ({', '.join(sorted(IMG_EXTS))})")
        n += 1
        key = P.input_key(project, n, ext)
        ct = mimetypes.guess_type(local)[0] or "application/octet-stream"
        store.upload(key, Path(local), content_type=ct)
        added.append({"key": key, "n": n, "from": local})
    return added


def input_keys(project: str) -> list[str]:
    """The pool's images, natural-sorted.

    **`engine/refs.py` hands these to a model positionally**, so the order
    `store.files` imposes is the reason `_10` does not arrive before `_2`.
    """
    prefix = P.input_prefix(project)
    return [f"{prefix}/{e['name']}" for e in store.files(prefix)
            if os.path.splitext(e["name"])[1].lower() in IMG_EXTS]


# ── CLI ─────────────────────────────────────────────────────────────────────

@click.group(help=__doc__)
def main():
    pass


def _warn_ignored_expiry(expires: int) -> None:
    """`--expires` is accepted and ignored, loudly. See `objects/presign.py`."""
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
@click.option("--json", "json_", is_flag=True)
def do_list(json_):
    """Every project."""
    names = P.list_projects()
    if json_:
        print(json.dumps([read_project(n) or {"name": n} for n in names], indent=2))
    elif names:
        for n in names:
            doc = read_project(n) or {}
            chars = ", ".join(doc.get("characters") or []) or "—"
            print(f"{n:<20} characters: {chars}")
    else:
        print("(no projects yet — create one with `studio projects new <project>`)",
              file=sys.stderr)


@main.command("new")
@click.argument("project", required=True)
@click.option("--character", "characters", multiple=True,
              help="A character this project involves. Repeatable.")
@click.option("--description", default='')
def do_new(project, characters, description):
    """Create a project record."""
    project = P.check_slug(project, "project name")
    if read_project(project):
        die(f"project {project!r} already exists")
    for c in characters:
        if c not in P.list_characters():
            die(f"no character {c!r} (see `studio character list`)")
    print(write_project({"name": project, "created": _now(),
                         "description": description,
                         "characters": sorted(characters)}))


@main.command("init")
@click.argument("project", required=True)
@click.option("--description", default='')
def do_init(project, description):
    """Write a project.json for a tree that predates the record."""
    project = P.check_slug(project, "project name")
    if read_project(project):
        die(f"project {project!r} already has a project.json")
    if project not in P.list_projects():
        die(f"nothing under {P.project_prefix(project)}/ — use `new` to create a project")
    # The characters are read back out of the runs rather than asked for: the
    # history already knows, and asking invites a wrong answer.
    from studio_pipeline.domain import runs as R
    chars: set[str] = set()
    for run_id in R.list_runs(project):
        chars.update(R.run_characters(project, run_id))
    print(write_project({"name": project, "created": _now(),
                         "description": description, "characters": sorted(chars)}))


@main.command("show")
@click.argument("project", required=True)
@click.option("--json", "json_", is_flag=True)
def do_show(project, json_):
    """A project's record, and what it holds."""
    project = P.check_slug(project, "project name")
    doc = read_project(project) or {
        "name": project,
        "note": "no project.json — created before the record existed"}
    counts = {kind: len(P.list_ids(P.project_dir_prefix(project, kind)))
              for kind in ("runs", "scenes", "movies")}
    counts["input"] = len(input_keys(project))
    counts["chains"] = len(store.files(P.chains_prefix(project)))
    # `--json` changes nothing here: the record is JSON either way. The flag
    # exists so a caller can pass it uniformly across every command.
    print(json.dumps({**doc, "holds": counts}, indent=2))


@main.command("add-inputs")
@click.argument("files", nargs=-1, required=True)
@click.argument("project", required=True)
@click.option("--json", "json_", is_flag=True)
def do_add_inputs(files, project, json_):
    """Add local file(s) to a project's input pool."""
    project = P.check_slug(project, "project name")
    added = add_inputs(project, files)
    if json_:
        print(json.dumps(added, indent=2))
    else:
        for a in added:
            print(a["key"])


@main.command("inputs")
@click.argument("project", required=True)
@click.option("--expires", type=int, default=3600)
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
def do_inputs(project, expires, json_, presign):
    """The project's input pool, as keys or as temporary URLs.

    `--presign` reaches `store` inline for the reason `runs outputs` does: the
    flag's parameter shadows anything of the same name in this scope, and
    `cli_surface_reference.json` records the dest, so renaming it is not on
    offer.
    """
    project = P.check_slug(project, "project name")
    _warn_ignored_expiry(expires)
    keys = input_keys(project)
    if not keys:
        print(f"(project {project} has no input pool yet)", file=sys.stderr)
        return
    if presign:
        urls = [store.presign(k) for k in keys]
        print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
    elif json_:
        print(json.dumps(keys, indent=2))
    else:
        print("\n".join(keys))
