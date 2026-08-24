"""A local record of what has already been submitted, so it is not paid for twice.

**The failure this exists for, in full.** A batch of 72 upscales was driven by a
shell script. The harness running it reported the job finished when it had not,
a second pass was started over the same list, and both ran to completion —
roughly 46 images were generated twice and about $2.30 was spent on results that
overwrote each other. Nothing anywhere noticed that an identical submission had
just been made: `run` builds a payload and sends it, and every send is the first
one as far as the pipeline is concerned.

**Why this is local and not a query.** The obvious place for it is the run
store, and `GET /api/runs` is one call — but the listing rows are a deliberately
small projection and do not carry the payload, so comparing would mean one
`GET /api/runs/<id>` per candidate run. For a 72-image batch against a project
that already holds 72 runs, that is on the order of 1800 requests before the
first submit. The right server-side answer is to project a fingerprint onto the
listing row and filter on it; that changes a deployed service and a DynamoDB
projection, so it is left as its own change.

What this catches is what actually happened: the same machine submitting the
same payload twice, minutes apart, from two shells. What it does not catch is a
second machine, or a colleague. It is a guard rail, not a lock, and `--again`
walks straight past it — the point is that walking past is a decision somebody
makes rather than something a script does in silence.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path

from studio_pipeline import profiles
from studio_pipeline.adapters import auth

#: Entries older than this are dropped when the file is next written. A
#: fortnight is long enough to cover "did I already run this batch yesterday?"
#: and short enough that the file stays small without anything sweeping it.
MAX_AGE_SECONDS = 14 * 24 * 60 * 60

#: A hard cap as well, because age alone does not bound a busy fortnight.
MAX_ENTRIES = 5000


def path() -> Path:
    """Per profile, for the reason sessions are: dev and prod are different
    libraries and a fingerprint from one says nothing about the other.

    Reads `auth.CONFIG_DIR` through the module rather than importing the
    constant, so redirecting the config dir in one place redirects this too.
    The suite used to reach the developer's real `credentials` file for exactly
    the opposite reason — a constant bound at import that a fixture could not
    reach — and a second file in that directory should not repeat it.
    """
    return auth.CONFIG_DIR / f"submissions-{profiles.current() or 'unset'}.json"


def fingerprint(model: str, payload: dict, bindings: dict) -> str:
    """What makes two submissions the same one.

    Model, inputs and bound images. `sort_keys` because a dict's order is not
    part of what was asked for, and two payloads built by different code paths
    should not read as different requests.

    The project is deliberately NOT in here — it is in the lookup key instead,
    so the same payload against a different project is a different submission
    and reads as one.
    """
    material = json.dumps({"model": model, "input": payload, "bindings": bindings},
                          sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def _read() -> dict:
    try:
        data = json.loads(path().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(entries: dict) -> None:
    now = time.time()
    fresh = {k: v for k, v in entries.items()
             if now - float(v.get("at") or 0) < MAX_AGE_SECONDS}
    if len(fresh) > MAX_ENTRIES:
        keep = sorted(fresh.items(), key=lambda kv: kv[1].get("at") or 0)[-MAX_ENTRIES:]
        fresh = dict(keep)
    auth.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # 600 before anything goes in, as the credentials file is: this holds run
    # ids and project slugs, which is not secret but is nobody else's business.
    fd = os.open(path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as handle:
        json.dump(fresh, handle)


def _key(project_id: str, digest: str) -> str:
    return f"{project_id}:{digest}"


def seen(project_id: str, digest: str) -> dict | None:
    """The earlier submission of this exact payload, or None."""
    return _read().get(_key(project_id, digest))


def record(project_id: str, digest: str, *, run: str, name: str) -> None:
    """Note a submission. Called after the run record exists, never before —
    a payload that was refused was not submitted and must not block a retry."""
    entries = _read()
    entries[_key(project_id, digest)] = {"run": run, "name": name, "at": time.time()}
    try:
        _write(entries)
    except OSError:
        # A ledger that cannot be written must not stop work. It is a guard
        # rail; losing it costs a duplicate, and refusing to generate because a
        # cache file is unwritable costs the whole command.
        pass
