"""Writing `models.json` — the repo file, not the served registry.

**Deliberately a separate module from `registry.py`, which only reads.** Reading
goes through `GET /api/models`, so it works against whichever environment is
selected and needs no checkout at all. Writing is the opposite kind of act: it
edits a file in this repository, it is reviewed in a pull request, and it takes
effect in production when the backend deploys. Two verbs on one module would
have invited a caller to write what it had just read over HTTP, which is how a
registry ends up with a deployed copy that disagrees with the committed one.

Only two commands write, and both are really doing the same thing — asking
Replicate what a model accepts and recording the answer:

    studio add-model <owner>/<name>   the entry, once
    studio models refresh             the schema snapshots, repeatedly

Both need `REPLICATE_API_TOKEN`, which is the CLI's and not the deployed
service's, so both stay here rather than becoming routes. `routes/models.py`
says the same thing from the other side.

**The file is under `backend/` now.** It was `engine/models.json` in this
package, and it moved so that one copy could serve the API, the SPA and this CLI
at once. `STUDIO_DIR` finds it — never a count of `".."` segments, which is right
for exactly one file's depth and broke every time something moved.
"""

from __future__ import annotations

import json

from studio_pipeline import STUDIO_DIR

#: The committed registry. Redirected per-test by `tests/conftest.py`, because
#: `models refresh` rewrites it in place and the dispatch test invokes every leaf
#: command there is — which once deleted 391 lines of schema.
PATH = str(STUDIO_DIR / "backend" / "studio_core" / "models.json")


class RegistryFileError(Exception):
    """The registry file is missing, malformed, or was asked for an unknown model."""


def read() -> dict:
    """The whole document, as committed."""
    try:
        with open(PATH) as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise RegistryFileError(f"registry not found at {PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryFileError(f"{PATH} is not valid JSON: {exc}") from exc


def write(data: dict) -> None:
    """Rewrite it, in the encoding it is committed in.

    `indent=2, ensure_ascii=False`, trailing newline — the same settings it was
    written with, so a change to one entry diffs as one entry rather than as the
    whole file re-encoded.
    """
    with open(PATH, "w") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def add(key: str, entry: dict) -> None:
    """Record a new model. Refuses a key that is taken."""
    data = read()
    if key in data.get("models", {}):
        raise RegistryFileError(f"registry key {key!r} is taken; pass --key to choose another.")
    data["models"][key] = entry
    write(data)


def save_snapshot(key: str, snapshot: dict) -> None:
    """Write a refreshed schema snapshot for one model, preserving file order.

    Only `snapshot` is ever rewritten — the structural fields are hand-curated
    and must survive a refresh untouched.
    """
    data = read()
    if key not in data.get("models", {}):
        raise RegistryFileError(f"cannot snapshot unknown model {key!r}")
    data["models"][key]["snapshot"] = snapshot
    write(data)
