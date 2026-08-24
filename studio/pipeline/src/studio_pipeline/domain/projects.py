"""`studio projects` — a PROJECT is the unit of production, and this manages them.

A project is a row with a UUID and a slug, and a folder node hanging off it:

    <project>/            ← the folder the record names as `root`
        runs/  scenes/  movies/  chains/  input/

Those five are a **starting layout, not a schema**. The record holds one node id
and no map of blessed folder names, so a person may rename `input/`, delete
`chains/` or add their own — and nothing breaks, because every run, scene and
movie names its own folder node rather than a path built from a convention.

PROJECT vs CHARACTER
--------------------
A character is an identity record; a project is a piece of work. They used to be
the same folder, which meant work involving two characters had nowhere to live
and work involving none had to borrow a fake character called `misc`. Involvement
is now `PROJ#…/CHAR#…` rows, which makes the reverse question — *which projects
involve this character* — answerable for the first time at any price.

Nothing is inferred: every generating command takes an explicit `--project`.
Guessing where output lands is the one thing that cannot be undone by rerunning a
command, so the answer is always asked for rather than assumed.

THE INPUT POOL LOST ITS NUMBERING, AND THAT IS THE POINT
--------------------------------------------------------
Pool basenames were `<project>_in_<n>.<ext>`, and `--input 3` meant "the file
whose name ends `_3`". So a deletion either renumbered every file — rewriting
every record that cited one — or left a hole that silently changed what
`--input 3` referred to.

**`--input N` is now position N in `GET /api/projects/<id>/inputs`.** The API
orders the pool; nothing here re-sorts it, and a file may be called anything.
Adding one is an ordinary upload into a folder.

CLI
---
    studio projects list
    studio projects new <project> --character <name> --description "…"
    studio projects show <project>
    studio projects rename <project> <new>
    studio projects link / unlink <project> <character>
    studio projects add-inputs <project> file.png [file2.png …]
    studio projects inputs <project> [--json|--presign]
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
from pathlib import Path

import click

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}


# ── the record ──────────────────────────────────────────────────────────────

def resolve(project: str) -> dict:
    """A slug or an id -> the project record. One call.

    Slug resolution is `GET /api/projects/slug:<slug>` — two reads server-side
    against a claim row, where it used to be a folder listing plus a document
    fetch. The caller gets the whole record, so nothing goes back for it.
    """
    if project and project.startswith("proj-"):
        return entities.get_project(project)
    P.check_slug(project, "project name")
    return entities.get_project(entities.address(project))


def require_project(project: str | None) -> dict:
    """The one place a missing `--project` becomes a usable error.

    It lists what exists, because the useful answer to "which project?" is the
    set of real options, not the name of the flag that was left out.
    """
    if not project:
        have = [p["slug"] for p in entities.list_projects()]
        die("no project given. Every generating command needs --project.\n"
            f"       existing projects: {', '.join(have) or '(none yet)'}\n"
            "       create one with: studio projects new <project>")
    try:
        return resolve(project)
    except api.NotFound:
        die(f"no project {project!r} (see `studio projects list`)")
    except P.PathError as exc:
        die(str(exc))


# ── the input pool ──────────────────────────────────────────────────────────

def input_pool(record: dict) -> list[dict]:
    """The pool, in the order that defines `--input N`.

    Position, not a filename number. Each entry carries `position` from the API,
    so a caller printing the pool and a caller resolving `--input 3` cannot
    disagree about what position three is.
    """
    return entities.project_inputs(record["id"])


def input_nodes(record: dict, numbers: list[int]) -> list[str]:
    """Resolve pool positions to node ids, in the order asked for."""
    pool = input_pool(record)
    by_position = {entry.get("position", n): entry["id"]
                   for n, entry in enumerate(pool, 1)}
    missing = [n for n in numbers if n not in by_position]
    if missing:
        raise KeyError(f"not in project {record['slug']}'s input pool: {missing} "
                       f"(it holds {len(pool)})")
    return [by_position[n] for n in numbers]


def add_inputs(record: dict, paths: list[str]) -> list[dict]:
    """Upload local files into the pool, keeping their own basenames.

    **No renaming**, where every file used to be renumbered into
    `<project>_in_<n>`. A pool position is a listing position now, so a name
    carries no meaning and throwing away the one it arrived with would only lose
    information.

    The pool folder is resolved by name under the project's root and created if
    someone removed it — the self-healing the layout section describes.
    """
    pool = store.ensure_child_folder(record["root"], P.INPUT_FOLDER)
    added = []
    for local in paths:
        if not os.path.isfile(local):
            die(f"not a file: {local}")
        ext = os.path.splitext(local)[1].lower()
        if ext not in IMG_EXTS:
            die(f"{local}: the input pool holds images ({', '.join(sorted(IMG_EXTS))})")
        ct = mimetypes.guess_type(local)[0] or "application/octet-stream"
        node = store.upload_into(pool["id"], os.path.basename(local), Path(local),
                                 content_type=ct)
        added.append({"node": node["id"], "name": os.path.basename(local),
                      "from": local})
    for position, entry in enumerate(input_pool(record), 1):
        for one in added:
            if one["node"] == entry["id"]:
                one["position"] = position
    return added


# ── CLI ─────────────────────────────────────────────────────────────────────

@click.group(help=__doc__)
def main():
    pass


def _character_ids(names) -> list[str]:
    ids = []
    for name in names:
        try:
            ids.append(entities.resolve_character(name)["id"])
        except api.NotFound:
            die(f"no character {name!r} (see `studio character list`)")
    return ids


@main.command("list")
@click.option("--json", "json_", is_flag=True)
def do_list(json_):
    """Every project. **One query**, where this listed folders and read a document each."""
    found = entities.list_projects()
    if json_:
        print(json.dumps(found, indent=2))
    elif found:
        for record in found:
            chars = ", ".join(record.get("character_slugs") or []) or "—"
            counts = record.get("counts") or {}
            print(f"{record['slug']:<20} {record.get('title', ''):<24} "
                  f"characters: {chars:<24} "
                  f"runs {counts.get('runs', 0)}  scenes {counts.get('scenes', 0)}  "
                  f"movies {counts.get('movies', 0)}")
    else:
        print("(no projects yet — create one with `studio projects new <project>`)",
              file=sys.stderr)


@main.command("new")
@click.argument("project", required=True)
@click.option("--character", "characters", multiple=True,
              help="A character this project involves. Repeatable.")
@click.option("--description", default='')
@click.option("--title", default='')
def do_new(project, characters, description, title):
    """Create a project: the record, its slug claim, its root and five subfolders.

    All of it in one transaction — either the project exists completely or it
    does not exist at all. The subfolders used to appear lazily, on whatever
    write happened to need one first, so a project could exist with no `runs/`.
    """
    try:
        P.check_slug(project, "project name")
        record = entities.create_project(
            project, title=title, description=description,
            characters=_character_ids(characters))
    except P.PathError as exc:
        die(str(exc))
    except api.Conflict:
        die(f"project {project!r} already exists")
    print(f"created project {record['slug']}  ({record['id']})")
    print("  " + "  ".join(f"{d}/" for d in P.PROJECT_DIRS))


@main.command("show")
@click.argument("project", required=True)
@click.option("--json", "json_", is_flag=True)
def do_show(project, json_):
    """A project's record, and what it holds."""
    record = require_project(project)
    counts = dict(record.get("counts") or {})
    counts["input"] = len(input_pool(record))
    if json_:
        print(json.dumps({**record, "counts": counts}, indent=2))
        return
    print(f"{record['slug']}  ({record['id']})  rev {record.get('rev')}")
    print(f"  title       {record.get('title') or '—'}")
    print(f"  characters  {', '.join(record.get('character_slugs') or []) or '—'}")
    print(f"  runs {counts.get('runs', 0)} · scenes {counts.get('scenes', 0)} · "
          f"movies {counts.get('movies', 0)}")
    print(f"  input pool  {counts['input']} image(s)")


@main.command("rename")
@click.argument("project", required=True)
@click.argument("new", required=True)
def do_rename(project, new):
    """Give a project a new slug. **New, and trivial — it was impossible before.**

    One `PATCH`: the old claim goes, the new one is written under
    `attribute_not_exists`, the record updates and the root folder is renamed,
    atomically. No object is copied and no record anywhere is rewritten, because
    every run, scene and movie names the project by **id**.
    """
    record = require_project(project)
    try:
        P.check_slug(new, "project name")
        after = entities.patch_project(record["id"], record["rev"], slug=new)
    except P.PathError as exc:
        die(str(exc))
    except api.Conflict as exc:
        die(str(exc))
    print(f"renamed {record['slug']} → {after['slug']}")
    print("  0 objects copied · 0 records rewritten")


@main.command("link")
@click.argument("project", required=True)
@click.argument("character", required=True)
def do_link(project, character):
    """Record that a project involves a character. **New — maintained explicitly.**

    It used to be a list inside `project.json`, which made the reverse question
    unanswerable and let a character be deleted while work still cited it. It is
    a row, readable from either end.
    """
    record = require_project(project)
    char = _character_ids([character])[0]
    current = list(record.get("characters") or [])
    if char in current:
        print(f"{character} is already linked to {record['slug']}", file=sys.stderr)
        return
    entities.put_project_characters(record["id"], current + [char])
    print(f"linked {character} → {record['slug']}")


@main.command("unlink")
@click.argument("project", required=True)
@click.argument("character", required=True)
def do_unlink(project, character):
    """Remove an involvement link. The files and the runs are untouched."""
    record = require_project(project)
    char = _character_ids([character])[0]
    current = list(record.get("characters") or [])
    if char not in current:
        die(f"{character} is not linked to {record['slug']}")
    entities.put_project_characters(record["id"],
                                    [c for c in current if c != char])
    print(f"unlinked {character} from {record['slug']}")


@main.command("delete")
@click.argument("project", required=True)
@click.option("--files", type=click.Choice(["keep", "delete"]), default="keep",
              help="What to do with the project's folder (default: keep it).")
@click.option("--cascade", is_flag=True,
              help="Delete the runs, scenes and movies it holds, then the project.")
@click.option("--force", is_flag=True, hidden=True,
              help="Delete the project and ORPHAN its children. Prefer --cascade.")
def do_delete(project, files, cascade, force):
    """Delete a project, and with --cascade everything it holds.

    **`--files keep` is the default deliberately.** The reverse default loses
    media to a typo; an orphaned folder in the library root is visible and
    recoverable.

    **Refuses while the project holds runs, and `--cascade` is the way through.**
    It deletes the movies, then the scenes, then the runs, then the project —
    children before the record that lists them, so an interruption leaves a
    project holding fewer of them rather than runs naming a project that is
    gone. `--force` is the old escape hatch and produces exactly that broken
    state; it is hidden and kept only for anything already using it.
    """
    record = require_project(project)
    try:
        result = entities.delete_project(record["id"], files=files,
                                         cascade=cascade, force=force)
    except api.Conflict as exc:
        die(f"{exc}\n       pass --cascade to delete them with it")
    removed = (result or {}).get("removed") or {}
    detail = ", ".join(f"{n} {k}(s)" for k, n in sorted(removed.items()))
    print(f"deleted project {record['slug']} (files: {files})"
          + (f" and {detail}" if detail else ""))


@main.command("add-inputs")
@click.argument("files", nargs=-1, required=True)
@click.argument("project", required=True)
@click.option("--json", "json_", is_flag=True)
def do_add_inputs(files, project, json_):
    """Add local file(s) to a project's input pool, keeping their basenames."""
    record = require_project(project)
    added = add_inputs(record, files)
    if json_:
        print(json.dumps(added, indent=2))
    else:
        for one in added:
            print(f"{one['name']}  ->  position {one.get('position', '?')}  "
                  f"{one['node']}")


@main.command("inputs")
@click.argument("project", required=True)
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
def do_inputs(project, json_, presign):
    """The input pool, with positions shown — because `--input N` is a position.

    `--presign` reaches `store` inline for the reason `runs outputs` does: the
    flag's parameter shadows anything of the same name in this scope, and
    `cli_surface_reference.json` records the dest, so renaming it is not on
    offer.
    """
    record = require_project(project)
    pool = input_pool(record)
    if not pool:
        print(f"(project {record['slug']} has no input pool yet)", file=sys.stderr)
        return
    if presign:
        urls = [store.presign_node(entry["id"]) for entry in pool]
        print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
    elif json_:
        print(json.dumps(pool, indent=2))
    else:
        for position, entry in enumerate(pool, 1):
            print(f"{position:>3}  {entry['id']}  {entry['name']}")
