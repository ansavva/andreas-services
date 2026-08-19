"""`studio rewrite` — when an object moves, the records that NAME it must follow.

Run records, scene and movie manifests and chain files all store S3 keys. That
is deliberate (keys are stable; presigned URLs expire and leak access), but it
means moving an object silently invalidates every document that cited it.

That is not hypothetical: the layout migration found 69 references that had been
dangling for weeks because `curate.py` renumbered reference images after the
runs that cited them. Nothing was wrong with the renumbering — there was just no
step that carried the records along with it. This is that step.

Anything that moves objects — the migrator, curate — calls `apply_moves()` with
{old key: new key}, and every document in the bucket that mentions an old key is
rewritten. Documents are the only place keys live, so this is complete.

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

from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.domain import paths as P

# Documents whose CONTENT names S3 keys. Everything else is opaque bytes.
DOC_NAMES = {"request.json", "result.json", "scene.json", "movie.json"}


def is_document(key: str) -> bool:
    if os.path.basename(key) in DOC_NAMES:
        return True
    return "/chains/" in key and key.endswith(".json")


def all_documents(s3) -> list[str]:
    """Every key-bearing document in the tree."""
    out = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3c.BUCKET, Prefix=s3c.key(P.PROJECTS + "/")):
        for obj in page.get("Contents", []):
            if is_document(obj["Key"]):
                out.append(obj["Key"])
    return out


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


def apply_moves(s3, mapping: dict[str, str], apply: bool = False) -> dict:
    """Rewrite every document that names a moved key.

    Returns {document: fields changed} for the ones that matched, so a caller
    can report exactly which history it touched rather than a bare count.
    """
    if not mapping:
        return {}
    touched: dict[str, int] = {}
    for key in all_documents(s3):
        body = s3.get_object(Bucket=s3c.BUCKET, Key=key)["Body"].read()
        try:
            doc = json.loads(body)
        except json.JSONDecodeError:
            continue
        n = _walk(doc, mapping)
        if not n:
            continue
        touched[key] = n
        if apply:
            s3.put_object(Bucket=s3c.BUCKET, Key=key,
                          Body=(json.dumps(doc, indent=2) + "\n").encode(),
                          ContentType="application/json")
    return touched


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


def project_docs(s3) -> list[str]:
    """Every `project.json`.

    `is_document` excludes them on purpose — they store no S3 keys, so
    `apply_moves` has nothing to do there. They do carry a `characters` list.
    """
    out = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3c.BUCKET, Prefix=s3c.key(P.PROJECTS + "/")):
        for obj in page.get("Contents", []):
            if os.path.basename(obj["Key"]) == "project.json":
                out.append(obj["Key"])
    return out


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


def rename_character(s3, old: str, new: str, apply: bool = False) -> dict:
    """Carry a character's new name into every record that names it.

    Returns {document: fields changed}, so a caller reports which history it
    touched rather than a bare count.
    """
    touched: dict[str, int] = {}
    for key in all_documents(s3) + project_docs(s3):
        body = s3.get_object(Bucket=s3c.BUCKET, Key=key)["Body"].read()
        try:
            doc = json.loads(body)
        except json.JSONDecodeError:
            continue
        n = _rename_fields(doc, old, new)
        if not n:
            continue
        touched[key] = n
        if apply:
            s3.put_object(Bucket=s3c.BUCKET, Key=key,
                          Body=(json.dumps(doc, indent=2) + "\n").encode(),
                          ContentType="application/json")
    return touched


# ── the standing integrity check ────────────────────────────────────────────

KEY_ROOTS = (P.CHARACTERS + "/", P.PROJECTS + "/", "phrasebook/")


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


def check(s3) -> dict:
    """Which recorded keys no longer resolve, and which record names them."""
    resolved: dict[str, bool] = {}
    dangling: list[dict] = []
    checked = 0
    docs = all_documents(s3)
    for doc_key in docs:
        try:
            doc = json.loads(s3.get_object(Bucket=s3c.BUCKET, Key=doc_key)["Body"].read())
        except json.JSONDecodeError:
            continue
        for ref in collect_keys(doc):
            checked += 1
            if ref not in resolved:
                try:
                    s3.head_object(Bucket=s3c.BUCKET, Key=ref)
                    resolved[ref] = True
                except Exception:
                    resolved[ref] = False
            if not resolved[ref]:
                dangling.append({"record": doc_key, "missing": ref})
    return {"documents": len(docs), "references": checked,
            "distinct": len(resolved), "dangling": dangling}


@click.group(help=__doc__)
def main():
    pass


@main.command("check")
@click.option("--json", "json_", is_flag=True)
def do_check(json_):
    """Report records that name an object which is no longer there."""
    report = check(s3c.client())
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
