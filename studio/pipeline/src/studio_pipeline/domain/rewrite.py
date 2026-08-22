"""`studio rewrite` — when a record's subject moves, the records that NAME it follow.

Run records, scene and movie manifests and chain files all store **paths**. That
is deliberate (a path is stable and readable; a presigned URL expires and leaks
access), but it means renaming or reparenting anything silently invalidates
every document that cited it.

That is not hypothetical: the layout migration found 69 references that had been
dangling for weeks because `curate.py` renumbered reference images after the
runs that cited them. Nothing was wrong with the renumbering — there was just no
step that carried the records along with it. This is that step.

WHY THIS SURVIVED THE CATALOG
-----------------------------
**#306 expected this module's move path to be deleted**, on the reasoning that
under the catalog nothing moves: a rename is a row update and the blob never
budges. The first half is true — `curate` writes no objects now — and the
conclusion still does not follow.

A record does not name a node. It names a path, checked against
`runs.KEY_ROOTS` and rebuilt by `runs.resolve_output_keys` out of a folder and a
name. So a node renamed in place leaves every path that cited it unresolvable,
which is the same dangling record for a different reason.

What retires this is records naming **node ids** — an id survives a rename by
construction. That is #420, open, and it is not small: it moves the binding
invariant, the runref vocabulary, and the terms every `SKILL.md` is written in.
Until it is decided, `curate` carries the records along (`curate.py` states the
same thing from the other side).

Anything that moves a record's subject — the migrator, curate, a character
rename — calls `apply_moves()` with {old path: new path}, and every document
that mentions an old path is rewritten. Documents are the only place paths live,
so this is complete.

A character rename needs a second pass, `rename_character()`, and cannot reuse
the first: records also name a character in a `characters:`/`character:` field,
where the value is a slug rather than a key. Swapping those through the same
context-free mapping would rename a project that happens to share the name —
which one does in the real bucket.

    studio rewrite check          # every recorded key resolves?
    studio rewrite check --json

`check` is the standing version of the migration's verify step: it walks every
record and confirms the object it names is still there. Run it after any manual
S3 surgery.
"""
from __future__ import annotations

import json
import os

import click

from studio_pipeline.adapters import api, store
from studio_pipeline.domain import paths as P

# Documents whose CONTENT names S3 keys. Everything else is opaque bytes.
DOC_NAMES = {"request.json", "result.json", "scene.json", "movie.json"}


def is_document(key: str) -> bool:
    if os.path.basename(key) in DOC_NAMES:
        return True
    return "/chains/" in key and key.endswith(".json")


def all_documents() -> list[str]:
    """Every path-bearing document in the tree.

    `store.walk_files` descends folder by folder where this was one paginated
    `list_objects_v2` — see its docstring for why the catalog has no prefix
    scan. This is the widest walk in the package and it is a maintenance
    command; nothing on a hot path does it.
    """
    return [path for path in store.walk_files(P.PROJECTS) if is_document(path)]


def _walk(node, mapping: dict[str, str]) -> int:
    """Replace every mapped key string in place. Returns how many changed."""
    changed = 0
    if isinstance(node, dict):
        items = list(node.items())
        for k, v in items:
            if isinstance(v, str) and v in mapping:
                node[k] = mapping[v]
                changed += 1
            else:
                changed += _walk(v, mapping)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str) and v in mapping:
                node[i] = mapping[v]
                changed += 1
            else:
                changed += _walk(v, mapping)
    return changed


def apply_moves(mapping: dict[str, str], apply: bool = False) -> dict:
    """Rewrite every document that names a moved key.

    Returns {document: fields changed} for the ones that matched, so a caller
    can report exactly which history it touched rather than a bare count.
    """
    if not mapping:
        return {}
    touched: dict[str, int] = {}
    for path in all_documents():
        doc = _load(path)
        if doc is None:
            continue
        n = _walk(doc, mapping)
        if not n:
            continue
        touched[path] = n
        if apply:
            _save(path, doc)
    return touched


def _load(path: str):
    """One document, or None if it is not JSON or not there any more."""
    try:
        return json.loads(store.read(path))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    except api.NotFound:
        # Listed a moment ago and gone now. A record that vanished mid-walk is
        # not this command's problem to report.
        return None


def _save(path: str, doc) -> None:
    """Write a document back, byte-for-byte in the shape the pipeline wrote it.

    `text/plain`, matching `POST /api/runs` and `runs.write_json`: these are
    bytes the pipeline reserves the right to reshape and nothing should be
    invited to parse. The trailing newline is kept because every existing
    document has one.
    """
    store.write(path, (json.dumps(doc, indent=2) + "\n").encode(),
                content_type="text/plain; charset=utf-8")


# ── a character rename ──────────────────────────────────────────────────────
#
# Records name a character in two ways, and only one of them is a key. The keys
# move with `apply_moves`; the NAME needs its own pass, and cannot share that
# one: a project may be called the same thing as a character (they are in the
# real bucket), so a context-free swap of every string equal to the old slug
# would rename the project along with it.

# The fields that record a character BY NAME: `characters: [...]` on a run,
# scene, movie or project, and the `character:` scalar a shoot writes.
CHARACTER_FIELDS = ("characters", "character")


def project_docs() -> list[str]:
    """Every `project.json`.

    `is_document` excludes them on purpose — they store no paths, so
    `apply_moves` has nothing to do there. They do carry a `characters` list.
    """
    return [path for path in store.walk_files(P.PROJECTS)
            if os.path.basename(path) == "project.json"]


def _rename_fields(node, old: str, new: str) -> int:
    """Swap the name in character-bearing fields only. Returns how many."""
    changed = 0
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k in CHARACTER_FIELDS:
                if v == old:
                    node[k] = new
                    changed += 1
                elif isinstance(v, list):
                    for i, entry in enumerate(v):
                        if entry == old:
                            v[i] = new
                            changed += 1
                else:
                    changed += _rename_fields(v, old, new)
            else:
                changed += _rename_fields(v, old, new)
    elif isinstance(node, list):
        for v in node:
            changed += _rename_fields(v, old, new)
    return changed


def rename_character(old: str, new: str, apply: bool = False) -> dict:
    """Carry a character's new name into every record that names it.

    Returns {document: fields changed}, so a caller reports which history it
    touched rather than a bare count.
    """
    touched: dict[str, int] = {}
    for path in all_documents() + project_docs():
        doc = _load(path)
        if doc is None:
            continue
        n = _rename_fields(doc, old, new)
        if not n:
            continue
        touched[path] = n
        if apply:
            _save(path, doc)
    return touched


# ── the standing integrity check ────────────────────────────────────────────

# The path roots a record may name. Mirrors `runs.KEY_ROOTS`, which is the
# writing half of the same rule — a binding that would fail there must be found
# here rather than counted as a stranger's string.
KEY_ROOTS = (P.CHARACTERS + "/", P.PROJECTS + "/", "phrasebook/", P.config_root())


def collect_keys(node) -> list[str]:
    """Every string in a document that is an S3 key of ours."""
    out: list[str] = []
    if isinstance(node, dict):
        for v in node.values():
            out += collect_keys(v)
    elif isinstance(node, list):
        for v in node:
            out += collect_keys(v)
    elif isinstance(node, str) and node.startswith(KEY_ROOTS) and "://" not in node:
        out.append(node)
    return out


def check() -> dict:
    """Which recorded paths no longer resolve, and which record names them.

    **The half of this module #306 keeps.** Its move path exists because paths
    dangle; this exists to find the ones that already have — after manual
    surgery, an interrupted `curate`, or anything that wrote the tree without
    going through a command.

    `store.exists` per distinct path, memoised, where this did a `head_object`.
    Same shape, one authorised request instead of one bucket read.
    """
    resolved: dict[str, bool] = {}
    dangling: list[dict] = []
    checked = 0
    docs = all_documents()
    for doc_path in docs:
        doc = _load(doc_path)
        if doc is None:
            continue
        for ref in collect_keys(doc):
            checked += 1
            if ref not in resolved:
                resolved[ref] = store.exists(ref)
            if not resolved[ref]:
                dangling.append({"record": doc_path, "missing": ref})
    return {"documents": len(docs), "references": checked,
            "distinct": len(resolved), "dangling": dangling}


@click.group(help=__doc__)
def main():
    pass


@main.command("check")
@click.option("--json", "json_", is_flag=True)
def do_check(json_):
    """Report records that name an object which is no longer there."""
    report = check()
    if json_:
        print(json.dumps(report, indent=2))
    else:
        print(f"documents        {report['documents']}")
        print(f"key references   {report['references']} ({report['distinct']} distinct)")
        print(f"dangling         {len(report['dangling'])}")
        for d in report["dangling"][:20]:
            print(f"  {d['record']}\n    -> {d['missing']}")
        if len(report["dangling"]) > 20:
            print(f"  … and {len(report['dangling']) - 20} more")
    if report["dangling"]:
        raise SystemExit(1)
