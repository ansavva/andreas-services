"""`studio phrasebook` — per-model wording lists: what to say instead of what.

A **wording list** is a small set of substitutions for one model: a phrase, and
the phrase to use in its place. Different models read the same idea
differently, so the phrasing that produces the intended result varies between
them, and that knowledge is tedious to rediscover.

IT WAS A YAML DOCUMENT AND IT IS NOW ROWS
-----------------------------------------
`phrasebook/wording.yaml` is gone. Each substitution is one row —
`LIB#<lib>` / `TERM#<model>#<avoid>` — which is what it always was: a per-model
list of avoid/use pairs is a table wearing a document.

**The concrete win is a failure that disappears.** The document was written
through `PATCH /api/text`, a route that overwrites an existing key and cannot
invent one, because studio's API has no upload and this was the one write in it
a person authors. So `studio phrasebook add` against a library that had never
held a `wording.yaml` was *refused* — the first entry anybody tried to record
was the one that could not be. The workaround was a seed copy in the repo and a
line in `dev-setup.sh` that pushed it only when the key was absent (#425),
carefully, because from the first `add` the bucket's copy was the live document
and a plain sync would have deleted its entries.

None of that exists any more. A row has no precondition: `add` on an empty
library writes one row and succeeds, and there is nothing for a sync to
clobber. Reading was never the broken half — a missing phrasebook read as an
empty one — and it still is not.

Two smaller things went with it. Uniqueness is now the key's: a duplicate
avoid-phrase for one model is a **409** rather than a second entry silently
appended beside the first, which is how the same phrase ended up recorded twice
with different replacements. And `rm` is possible at all — removing an entry
from a document meant rewriting the whole document, so nothing offered it.

SHAPE
-----
One row per pair::

    model      the model key from the studio registry
    avoid      the phrasing to replace
    use        the phrasing to use instead
    note       optional free text — where this came from
    replicate  <owner>/<name>, carried for display
    added      ISO date

CLI
---
    studio phrasebook show  [--model <key>]
    studio phrasebook terms --model <key>              # JSON, for tooling
    studio phrasebook check --model <key> --text "…"   # scan a draft
    studio phrasebook add   --model <key> --avoid "…" --use "…"
    studio phrasebook rm    --model <key> --avoid "…"
    studio phrasebook models
"""
from __future__ import annotations

import json

import click
import yaml

from studio_pipeline.adapters import api, entities
from studio_pipeline.errors import die


def by_model(model: str | None = None) -> dict[str, list[dict]]:
    """Every term, grouped by model key, in the order the API returned them.

    Grouped here rather than by the API because the grouping is a presentation
    fact — `show` and `models` want sections, `terms` and `check` want a flat
    list for one model, and only one of those shapes can be the wire's.
    """
    grouped: dict[str, list[dict]] = {}
    for term in entities.phrasebook(model=model):
        grouped.setdefault(term["model"], []).append(term)
    return grouped


def terms(model_key: str) -> list[dict]:
    """The avoid/use pairs for one model.

    One fetch, so a caller can check many fields locally and keep per-field
    attribution instead of making a round trip each time. The shape is pinned:
    `domain/prompt.py` and the engine both read exactly these two keys.
    """
    return [{"avoid": term["avoid"], "use": term["use"]}
            for term in entities.phrasebook(model=model_key) if term.get("avoid")]


def _section(rows: list[dict]) -> dict:
    """One model's rows as the block `show` prints.

    Deliberately the same shape the YAML document had — `replicate` plus
    `entries` — because that is what every `SKILL.md` example shows and what a
    person reading the output expects. The storage changed; the reading did not.
    """
    replicate = next((r["replicate"] for r in rows if r.get("replicate")), None)
    return {"replicate": replicate,
            "entries": [{k: r[k] for k in ("avoid", "use", "note", "added")
                         if r.get(k)} for r in rows]}


@click.group(help=__doc__)
def main():
    pass


@main.command("models")
def do_models():
    """List the models covered."""
    for model, rows in sorted(by_model().items()):
        replicate = next((r["replicate"] for r in rows if r.get("replicate")), "?")
        print(f"{model:20} {replicate or '?':40} entries={len(rows)}")


@main.command("terms")
@click.option("--model", required=True)
def do_terms(model):
    """The avoid/use pairs for one model, as JSON."""
    print(json.dumps(terms(model)))


@main.command("show")
@click.option("--model", help="limit to one model key")
def do_show(model):
    """Print the phrasebook."""
    grouped = by_model(model)
    if model and not grouped:
        die(f"no phrasebook section for {model!r}")
    print(yaml.safe_dump({k: _section(v) for k, v in sorted(grouped.items())},
                         sort_keys=False, allow_unicode=True))


@main.command("check")
@click.option("--model", required=True)
@click.option("--text", required=True)
def do_check(model, text):
    """Scan text against this model's wording list. Exits 1 on a hit."""
    rows = entities.phrasebook(model=model)
    if not rows:
        print(f"no wording list for {model}")
        return
    low = text.lower()
    # A row may carry an empty `avoid` only if something wrote one; skipping it
    # matters because "" is a substring of everything, and the check would then
    # refuse every draft it was ever shown.
    hits = [r for r in rows if r.get("avoid") and r["avoid"].lower() in low]
    if not hits:
        print(f"no substitutions apply ({len(rows)} entries)")
        return
    for row in hits:
        print(f"AVOID  {row['avoid']!r}\n  USE  {row['use']!r}"
              + (f"\n  note {row['note']}" if row.get("note") else ""))
    raise SystemExit(1)


@main.command("add")
@click.option("--avoid", required=True)
@click.option("--model", required=True)
@click.option("--note", default='', help="optional free text — where this came from")
@click.option("--replicate", help="owner/name, when first creating the section")
@click.option("--use", required=True)
def do_add(avoid, model, note, replicate, use):
    """Record a substitution.

    **This can no longer fail on a library that has never held a phrasebook.**
    See the module docstring: the write used to require a document to already
    exist, so the first entry anybody recorded was the one that was refused.
    """
    try:
        entities.add_phrasebook_term(model, avoid, use, note=note or None,
                                     replicate=replicate)
    except api.Conflict:
        die(f"{model} already records a substitution for {avoid!r} — "
            f"remove it first: studio phrasebook rm --model {model} "
            f"--avoid {avoid!r}")
    print(f"recorded {avoid!r} -> {use!r} for {model}")


@main.command("rm")
@click.option("--avoid", required=True)
@click.option("--model", required=True)
def do_rm(avoid, model):
    """Remove a substitution. **New — a document had to be rewritten whole.**"""
    try:
        entities.delete_phrasebook_term(model, avoid)
    except api.NotFound:
        die(f"{model} records no substitution for {avoid!r} "
            f"(see `studio phrasebook show --model {model}`)")
    print(f"removed {avoid!r} from {model}")
