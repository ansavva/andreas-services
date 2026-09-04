"""Name matching, address joining, the starting folder conventions, and the
angle-image paths.

**Nothing here builds a key.** An entity record names its own nodes: a
character holds one node id (`root`); a run holds `folder`, `outputs` and
`payload`. A caller that wants a character's `reference/` folder asks the
record for `root` and the tree for the child called `reference` — one listing,
no construction, and nothing that a rename can invalidate. A folder is not an
identity.

WHAT IS HERE, AND WHY EACH ONE EARNS IT
---------------------------------------
**`by_name`.** A name is a mutable, free-text label a person types; matching
one is a listing plus a match, client-side.

**`join`.** The CLI types addresses: `<name>/reference/face/<file>` is what a
person writes and what `GET /api/resolve?path=` turns into a node. That is an
**address**, not a key — resolving one is a lookup against the tree as it is
now, where building a key would assert where something must be.

**The starting layout names.** `CHAR_POOLS` and `PROJECT_DIRS` are what the API
creates with a new entity and what the CLI prints back. They are convention:
nothing afterwards requires them, a person may rename or delete any of them, and
an image is a reference because a tag on it says so rather than because of the
folder it sits in.

**The angle images.** `config/angle/{body,face}/*.png` belong to no character
and no project. They are **ordinary nodes**: the library is created with a
`config/` folder, `studio config sync` uploads them through the API like
anything else, and an angle image is recorded in a run's bindings like every
other image. The names stay here because the angle spec addresses angle images
by path.
"""
from __future__ import annotations

import re

# Neither a character nor a project: shared, generic material kept in the repo
# and copied out to S3. `ANGLE_GROUPS` mirrors the character reference groups it
# guides, so a `body` angle asks for a `body` image.
CONFIG = "config"
ANGLE_GROUPS = ("body", "face")

# The four folders a new character starts with. `reference` is not structural —
# reference-ness is a tag on the file, not a location — so these are a starting
# layout and nothing more. See the spec's "the folder layout is convention, not
# schema".
CHAR_POOLS = ("reference", "corpus", "seed", "archive")

# The five a new project starts with, on the same footing. `runs`, `scenes`,
# `movies` and `input` are resolved by name at write time and created if absent,
# so renaming one strands nothing: every existing run names its own folder node.
PROJECT_DIRS = ("runs", "scenes", "movies", "chains", "input")

INPUT_FOLDER = "input"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class PathError(Exception):
    pass


def by_name(records: list[dict], wanted: str, what: str) -> dict:
    """One record out of a listing, matched on its `name`. **Client-side.**

    A name is a free-text label, so resolving one is a listing plus a match,
    and it can find more than one.

    **Ambiguity is refused with the ids listed**, never guessed. Picking the
    first would make which record a command touched depend on sort order, which
    is the kind of thing nobody notices until it has written to the wrong one.

    It lives on the client because it is a convenience for a person typing, not
    an address: every wire call this package makes passes an id.
    """
    wanted_folded = " ".join((wanted or "").split()).lower()
    found = [record for record in records
             if " ".join((record.get("name") or "").split()).lower() == wanted_folded]
    if not found:
        raise PathError(f"no {what} called {wanted!r}")
    if len(found) > 1:
        listed = "\n".join(f"         {record['id']}" for record in found)
        raise PathError(
            f"{len(found)} {what}s are called {wanted!r} — names are not unique.\n"
            f"       pass one of these ids instead:\n{listed}")
    return found[0]


def join(*parts: str) -> str:
    """Join address segments, dropping the empty ones.

    An **address**, resolved by `GET /api/resolve?path=` against the tree as it
    actually is. Not a key: nothing here asserts where an object lives, and the
    result is thrown away the moment the node behind it is known.
    """
    return "/".join(p.strip("/") for p in parts if p not in (None, ""))


# ── shared material ─────────────────────────────────────────────────────────

def config_prefix(*parts: str) -> str:
    return join(CONFIG, *parts)


def angle_prefix(group: str) -> str:
    if group not in ANGLE_GROUPS:
        raise PathError(f"unknown angle group {group!r}; expected one of {list(ANGLE_GROUPS)}")
    return config_prefix("pose", group)


