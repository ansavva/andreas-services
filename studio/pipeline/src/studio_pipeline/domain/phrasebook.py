"""`studio phrasebook` — per-model wording lists: what to say instead of what.

A **wording list** is a small set of substitutions for one model: a phrase, and
the phrase to use in its place. Different models read the same idea differently,
so the phrasing that produces the intended result varies between them, and that
knowledge is tedious to rediscover.

It is kept **as data in S3, not in this repository**:

    phrasebook/wording.yaml

Same split the repo uses for characters — the tooling is code, the specifics are
data. This file holds only the machinery.

SHARED MATERIAL, SO NEITHER HALF USES A NODE (#305)
---------------------------------------------------
The phrasebook belongs to no character and no project, `catalog_seed.py`
deliberately records no node for it, and `store.resolve` therefore 404s on it.
Both directions go through the API's **key-addressed** routes instead:

    read    store.shared_read(KEY)          GET   /api/asset
    write   api.patch("/api/text", …)       PATCH /api/text

**The write cannot create the file, and the read used to be able to.**
`put_object` was happy to invent an object; `PATCH /api/text` requires the key
to name one that already exists, because studio's API has no upload and this is
the one write in it a person authors. So `studio phrasebook add` against a
library that has never held a `wording.yaml` fails instead of quietly starting
one, and `save` says what that takes.

**A fresh dev stack gets its first one from the repo (#425.)**
`studio/phrasebook/wording.yaml` is a seed copy, and `dev-setup.sh` puts it in
the bucket **only when the key is absent** — unlike the `config/` sync beside
it, because from the first `add` the bucket's copy is the live document and a
sync would delete its entries. Reading was never affected either way: a missing
phrasebook still reads as an empty one.

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
import json

import click
import yaml

from studio_pipeline.adapters import api, store  # noqa: E402
from studio_pipeline.domain import paths as P  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402

KEY = P.phrasebook_key()


def _empty() -> dict:
    """A fresh empty document.

    A function rather than a constant: every caller goes on to mutate what it
    is given, and a shared `{"models": {}}` would collect the first `add`'s
    section and hand it to the next reader.
    """
    return {"version": 1, "models": {}}


def load() -> dict:
    """The wording lists, or an empty document when there are none yet.

    **Only a 404 is "no phrasebook".** This used to catch every exception and
    grep the message for `NoSuchKey`, because a missing key surfaced differently
    across botocore versions — which made a refusal indistinguishable from an
    absent file, and the phrasebook then reports "no substitutions apply" for a
    draft it never checked. `api.Forbidden` is a different fact and is left to
    surface.
    """
    try:
        body = store.shared_read(KEY)
    except api.NotFound:
        return _empty()
    return yaml.safe_load(body) or _empty()


def save(doc: dict) -> str:
    """Write the wording list back through `PATCH /api/text`.

    **It can only overwrite.** The route refuses a key that names nothing, so
    this is where the one behaviour `put_object` had and the API does not gets
    reported rather than swallowed. See the module docstring.
    """
    doc["updated"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    try:
        api.patch("/api/text", {"key": KEY, "content": content})
    except api.NotFound:
        die(f"there is no {KEY} in this library, and the API cannot create one — "
            "it overwrites an existing file and never invents one. The repo "
            "ships a seed copy and dev-setup.sh puts it there when the key is "
            "absent, so re-run ./studio/scripts/dev-setup.sh.")
    return KEY


def terms(model_key: str) -> list[dict]:
    """The avoid/use pairs for one model.

    One fetch, so a caller can check many fields locally and keep per-field
    attribution instead of making a round trip each time.
    """
    section = (load().get("models") or {}).get(model_key) or {}
    return [{"avoid": e["avoid"], "use": e["use"]}
            for e in (section.get("entries") or []) if e.get("avoid")]


def _open():
    """The document and its model sections, loaded once.

    Every command needs both, and they were shared by living in one `_run`. A
    helper keeps that sharing without the dispatch.
    """
    doc = load()
    return doc, doc.setdefault("models", {})


@click.group(help=__doc__)
def main():
    pass


@main.command("models")
def do_models():
    """List the models covered."""
    _doc, models = _open()
    for k, v in models.items():
        print(f"{k:20} {v.get('replicate','?'):40} "
              f"entries={len(v.get('entries') or [])}")


@main.command("terms")
@click.option("--model", required=True)
def do_terms(model):
    """The avoid/use pairs for one model, as JSON."""
    print(json.dumps(terms(model)))


@main.command("show")
@click.option("--model", help="limit to one model key")
def do_show(model):
    """Print the phrasebook."""
    _doc, models = _open()
    if model and model not in models:
        die(f"no phrasebook section for {model!r}")
    out = {model: models[model]} if model else models
    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))


@main.command("check")
@click.option("--model", required=True)
@click.option("--text", required=True)
def do_check(model, text):
    """Scan text against this model's wording list. Exits 1 on a hit."""
    _doc, models = _open()
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
    doc, models = _open()
    section = models.setdefault(model, {"replicate": None, "entries": []})
    if replicate:
        section["replicate"] = replicate
    section.setdefault("entries", []).append({
        "avoid": avoid,
        "use": use,
        "note": note,
        "added": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
    })
    # The path, not an `s3://` URI: the CLI knows no bucket name any more, and
    # printing one it guessed would be worse than printing none.
    print(f"recorded -> {save(doc)}")
