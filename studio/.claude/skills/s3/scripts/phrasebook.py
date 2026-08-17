# /// script
# requires-python = ">=3.13"
# dependencies = ["boto3", "pyyaml"]
# ///
"""phrasebook.py — per-model wording lists: what to say instead of what.

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
    uv run phrasebook.py show  [--model <key>]
    uv run phrasebook.py terms --model <key>              # JSON, for tooling
    uv run phrasebook.py check --model <key> --text "…"   # scan a draft
    uv run phrasebook.py add   --model <key> --avoid "…" --use "…"
    uv run phrasebook.py models
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths as P  # noqa: E402
from s3_common import BUCKET, client, die  # noqa: E402

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-model wording lists.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("show", help="print the phrasebook")
    p.add_argument("--model", help="limit to one model key")

    p = sub.add_parser("models", help="list the models covered")

    p = sub.add_parser("terms", help="the avoid/use pairs for one model, as JSON")
    p.add_argument("--model", required=True)

    p = sub.add_parser("check", help="scan text against this model's wording list")
    p.add_argument("--model", required=True)
    p.add_argument("--text", required=True)

    p = sub.add_parser("add", help="record a substitution")
    p.add_argument("--model", required=True)
    p.add_argument("--avoid", required=True)
    p.add_argument("--use", required=True)
    p.add_argument("--note", default="", help="optional free text — where this came from")
    p.add_argument("--replicate", help="owner/name, when first creating the section")


    args = ap.parse_args()
    s3 = client()
    doc = load(s3)
    models = doc.setdefault("models", {})

    if args.cmd == "models":
        for k, v in models.items():
            print(f"{k:20} {v.get('replicate','?'):40} "
                  f"entries={len(v.get('entries') or [])}")
        return 0

    if args.cmd == "terms":
        # One fetch, so a caller can check many fields locally and keep
        # per-field attribution instead of making a round trip each time.
        section = models.get(args.model) or {}
        print(json.dumps([{"avoid": e["avoid"], "use": e["use"]}
                          for e in (section.get("entries") or []) if e.get("avoid")]))
        return 0

    if args.cmd == "show":
        out = {args.model: models[args.model]} if args.model else models
        if args.model and args.model not in models:
            die(f"no phrasebook section for {args.model!r}")
        print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
        return 0

    if args.cmd == "check":
        section = models.get(args.model)
        if not section:
            print(f"no wording list for {args.model}")
            return 0
        low = args.text.lower()
        # An entry may carry an empty `avoid` — a placeholder section. Skipping
        # it matters: "" is a substring of everything.
        hits = [e for e in (section.get("entries") or [])
                if e.get("avoid") and e["avoid"].lower() in low]
        if not hits:
            print(f"no substitutions apply ({len(section.get('entries') or [])} entries)")
            return 0
        for e in hits:
            print(f"AVOID  {e['avoid']!r}\n  USE  {e['use']!r}"
                  + (f"\n  note {e['note']}" if e.get("note") else ""))
        return 1

    section = models.setdefault(args.model, {"replicate": None, "entries": []})
    if args.replicate:
        section["replicate"] = args.replicate
    section.setdefault("entries", []).append({
        "avoid": args.avoid,
        "use": args.use,
        "note": args.note,
        "added": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
    })
    print(f"recorded -> s3://{BUCKET}/{save(s3, doc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
