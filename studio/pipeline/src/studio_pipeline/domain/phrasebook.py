"""`studio phrasebook` — per-model wording lists: what to say instead of what.

A **wording list** is a small set of substitutions for one model: a phrase, and
the phrase to use in its place. Different models read the same idea differently,
so the phrasing that produces the intended result varies between them, and that
knowledge is tedious to rediscover.

It is kept **as data in S3, not in this repository**:

    phrasebook/wording.yaml

Same split the repo uses for characters — the tooling is code, the specifics are
data. This file holds only the machinery.

SHAPE
-----
    version: 1
    models:
      <model key from the studio registry>:
        replicate: <owner>/<name>
        entries:
          - avoid: the phrasing to replace
            use:   the phrasing to use instead
            note:  optional free text — where this came from
            added: ISO date

CLI
---
    studio phrasebook show  [--model <key>]
    studio phrasebook terms --model <key>              # JSON, for tooling
    studio phrasebook check --model <key> --text "…"   # scan a draft
    studio phrasebook add   --model <key> --avoid "…" --use "…"
    studio phrasebook models
"""
from __future__ import annotations

import datetime as dt
import io
import json

import click
import yaml

from studio_pipeline.adapters.s3 import BUCKET, client, die  # noqa: E402
from studio_pipeline.domain import paths as P  # noqa: E402

KEY = P.phrasebook_key()


def load(s3) -> dict:
    try:
        body = s3.get_object(Bucket=BUCKET, Key=KEY)["Body"].read()
    except s3.exceptions.NoSuchKey:
        return {"version": 1, "models": {}}
    except Exception as exc:  # missing key surfaces differently across botocore versions
        if "NoSuchKey" in str(exc) or "404" in str(exc):
            return {"version": 1, "models": {}}
        raise
    return yaml.safe_load(io.BytesIO(body)) or {"version": 1, "models": {}}


def save(s3, doc: dict) -> str:
    doc["updated"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    s3.put_object(Bucket=BUCKET, Key=KEY,
                  Body=yaml.safe_dump(doc, sort_keys=False, allow_unicode=True).encode(),
                  ContentType="application/x-yaml")
    return KEY


def terms(s3, model_key: str) -> list[dict]:
    """The avoid/use pairs for one model.

    One fetch, so a caller can check many fields locally and keep per-field
    attribution instead of making a round trip each time.
    """
    section = (load(s3).get("models") or {}).get(model_key) or {}
    return [{"avoid": e["avoid"], "use": e["use"]}
            for e in (section.get("entries") or []) if e.get("avoid")]


def _open():
    """The document and its model sections, loaded once.

    Every command needs all three, and they were shared by living in one
    `_run`. A helper keeps that sharing without the dispatch.
    """
    s3 = client()
    doc = load(s3)
    return s3, doc, doc.setdefault("models", {})


@click.group(help=__doc__)
def main():
    pass


@main.command("models")
def do_models():
    """List the models covered."""
    _s3, _doc, models = _open()
    for k, v in models.items():
        print(f"{k:20} {v.get('replicate','?'):40} "
              f"entries={len(v.get('entries') or [])}")


@main.command("terms")
@click.option("--model", required=True)
def do_terms(model):
    """The avoid/use pairs for one model, as JSON."""
    s3, _doc, _models = _open()
    print(json.dumps(terms(s3, model)))


@main.command("show")
@click.option("--model", help="limit to one model key")
def do_show(model):
    """Print the phrasebook."""
    _s3, _doc, models = _open()
    if model and model not in models:
        die(f"no phrasebook section for {model!r}")
    out = {model: models[model]} if model else models
    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))


@main.command("check")
@click.option("--model", required=True)
@click.option("--text", required=True)
def do_check(model, text):
    """Scan text against this model's wording list. Exits 1 on a hit."""
    _s3, _doc, models = _open()
    section = models.get(model)
    if not section:
        print(f"no wording list for {model}")
        return
    low = text.lower()
    # An entry may carry an empty `avoid` — a placeholder section. Skipping
    # it matters: "" is a substring of everything.
    hits = [e for e in (section.get("entries") or [])
            if e.get("avoid") and e["avoid"].lower() in low]
    if not hits:
        print(f"no substitutions apply ({len(section.get('entries') or [])} entries)")
        return
    for e in hits:
        print(f"AVOID  {e['avoid']!r}\n  USE  {e['use']!r}"
              + (f"\n  note {e['note']}" if e.get("note") else ""))
    raise SystemExit(1)


@main.command("add")
@click.option("--avoid", required=True)
@click.option("--model", required=True)
@click.option("--note", default='', help="optional free text — where this came from")
@click.option("--replicate", help="owner/name, when first creating the section")
@click.option("--use", required=True)
def do_add(avoid, model, note, replicate, use):
    """Record a substitution."""
    s3, doc, models = _open()
    section = models.setdefault(model, {"replicate": None, "entries": []})
    if replicate:
        section["replicate"] = replicate
    section.setdefault("entries", []).append({
        "avoid": avoid,
        "use": use,
        "note": note,
        "added": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
    })
    print(f"recorded -> s3://{BUCKET}/{save(s3, doc)}")
