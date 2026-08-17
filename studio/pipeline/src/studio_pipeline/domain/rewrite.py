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

    studio rewrite check          # every recorded key resolves?
    studio rewrite check --json

`check` is the standing version of the migration's verify step: it walks every
record and confirms the object it names is still there. Run it after any manual
S3 surgery.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

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
def _cmd_check(json_):
    return _run(SimpleNamespace(cmd="check", json=json_))


def _run(args):

    report = check(s3c.client())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"documents        {report['documents']}")
        print(f"key references   {report['references']} ({report['distinct']} distinct)")
        print(f"dangling         {len(report['dangling'])}")
        for d in report["dangling"][:20]:
            print(f"  {d['record']}\n    -> {d['missing']}")
        if len(report["dangling"]) > 20:
            print(f"  … and {len(report['dangling']) - 20} more")
    return 1 if report["dangling"] else 0
