"""The journal a maintenance run writes, and reads back before it destroys.

Bookkeeping rather than logic: a run records what it found and what it did under
`studio/local/migrations/`, and the next run reads it. It matters because
`catalog reseat` is the one command here that can lose data and REFUSES to run
until the journal says a `verify` passed — so the journal is a gate, not a log.

Lifted out of `catalog_check.py` when the migration it was named for was
retired. `catalog gc` and `catalog reseat` are the callers now, and neither is a
migration.
"""
from __future__ import annotations

import datetime as dt
import json
import os

from studio_pipeline import STUDIO_DIR

#: Kept from the migration that named it. A run's journal is a local artefact
#: nobody shares, and renaming the directory would strand the ones on disk.
JOURNAL_DIR = str(STUDIO_DIR / "local" / "migrations")


def journal_path(name: str | None) -> str:
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    if name:
        return os.path.join(JOURNAL_DIR,
                            name if name.endswith(".json") else name + ".json")
    existing = sorted(f for f in os.listdir(JOURNAL_DIR) if f.endswith(".json"))
    if existing:
        return os.path.join(JOURNAL_DIR, existing[-1])
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(JOURNAL_DIR, f"{ts}.json")

def load_journal(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {}

def save_journal(path: str, doc: dict) -> None:
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)
