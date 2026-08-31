"""Slug rules, the starting folder conventions, and the shared-material keys.

**This module was 334 lines of key construction and is now a name checker.**
That is the single clearest measure of what the entity model changed, so the
history is worth stating rather than quietly deleting.

WHAT WAS HERE
-------------
`character_prefix`, `character_key`, `profile_key`, `char_pool_prefix`,
`character_of`, `project_prefix`, `project_key`, `project_json_key`,
`project_dir_prefix`, `runs_prefix`, `run_prefix`, `run_key`, `scenes_prefix`,
`scene_prefix`, `scene_key`, `movies_prefix`, `movie_prefix`, `movie_key`,
`chains_prefix`, `chain_key`, `input_prefix`, `input_basename`, `input_key`,
`phrasebook_key`, `list_characters`, `list_projects`, `list_ids`.

Every one of them built `characters/<slug>/…` or `projects/<slug>/…`, and every
one of them existed for the same reason: the slug WAS the primary key, so twelve
modules had to spell it identically or the tree forked. The module's own
docstring called that out — "moving a folder meant finding all of them" — and
solved the wrong half of the problem. The right half is that a folder should not
be an identity at all.

They are gone because **an entity record names its own nodes**. A character
holds one node id (`root`); a run holds `folder`, `outputs` and `payload`. A
caller that wants a character's `reference/` folder asks the record for `root`
and the tree for the child called `reference` — one listing, no construction,
and nothing that a rename can invalidate. `domain/rewrite.py` existed solely to
patch the documents these builders had scattered paths through, and it is gone
with them.

WHAT SURVIVES, AND WHY EACH ONE EARNS IT
----------------------------------------
**The slug rule.** A slug is still a real thing — a mutable, library-unique
label a person types — and it still has to be checkable before it is sent. It is
no longer a path segment, so the rule is about legibility rather than about S3.

**`join`.** The CLI still types addresses: `<slug>/reference/face/<file>` is what
a person writes and what `GET /api/resolve?path=` turns into a node. That is an
**address**, not a key, and the difference is the point of the whole change —
resolving one is a lookup against the tree as it is now, where building a key
asserted where something must be.

**The starting layout names.** `CHAR_POOLS` and `PROJECT_DIRS` are what the API
creates with a new entity and what the CLI prints back. They are convention:
nothing afterwards requires them, a person may rename or delete any of them, and
an image is a reference because a `REF#` row says so rather than because of the
folder it sits in.

**The angle images.** `config/angle/{body,face}/*.png` belong to no character and
no project. They are **ordinary nodes** now — spec phase 7 landed, the library is
created with a `config/` folder, and `studio config sync` uploads them through
the API like anything else. `shared_read`, `shared_presign` and the
`shared:<key>` submit marker are all gone with the key-addressed route they
used, and an angle image is recorded in a run's bindings like every other image. The
names stay here because the angle spec addresses angle images by path.

The phrasebook used to be listed beside them and is not: it is `TERM#` rows now,
so there is no `phrasebook/wording.yaml` to address.
"""
from __future__ import annotations

import re

# Neither a character nor a project: shared, generic material kept in the repo
# and copied out to S3. `ANGLE_GROUPS` mirrors the character reference groups it
# guides, so a `body` angle asks for a `body` image.
CONFIG = "config"
ANGLE_GROUPS = ("body", "face")

# The four folders a new character starts with. `reference` is no longer
# structural — reference-ness is a `REF#` row, not a location — so these are a
# starting layout and nothing more. See the spec's "the folder layout is
# convention, not schema".
CHAR_POOLS = ("reference", "corpus", "seed", "archive")

# The five a new project starts with, on the same footing. `runs`, `scenes`,
# `movies` and `input` are resolved by name at write time and created if absent,
# so renaming one strands nothing: every existing run names its own folder node.
PROJECT_DIRS = ("runs", "scenes", "movies", "chains", "input")

# Where a new run, scene or movie's folder is put, and where the input pool is
# read from. Named once because the API applies the same convention, and two
# copies of a convention drift.
RUN_PARENT = "runs"
SCENE_PARENT = "scenes"
MOVIE_PARENT = "movies"
INPUT_FOLDER = "input"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class PathError(Exception):
    pass


def check_slug(s: str, what: str = "name") -> str:
    """Characters, projects and scenes share one slug rule.

    **It is a legibility rule now, not a filesystem one.** A slug used to become
    a path segment, so the character set was about what S3 and a shell would
    tolerate. A slug is an attribute on a row today and could be anything; the
    rule is kept because a name that a person types, greps and pastes into a
    command still wants to be lowercase, unambiguous and free of spaces.
    """
    if not s or not NAME_RE.match(s):
        raise PathError(f"invalid {what} {s!r}; use lowercase [a-z0-9_-] starting alphanumeric")
    return s


def join(*parts: str) -> str:
    """Join address segments, dropping the empty ones.

    An **address**, resolved by `GET /api/resolve?path=` against the tree as it
    actually is. Not a key: nothing here asserts where an object lives, and the
    result is thrown away the moment the node behind it is known.
    """
    return "/".join(p.strip("/") for p in parts if p not in (None, ""))


# ── shared material: the last raw keys ──────────────────────────────────────

def config_root() -> str:
    """The `config/` prefix with its separator — what an angle image's path must
    start with. A caller writing `P.CONFIG + "/"` is spelling it a second time,
    which is the drift this exists to prevent.
    """
    return CONFIG + "/"


def config_prefix(*parts: str) -> str:
    return join(CONFIG, *parts)


def angle_prefix(group: str) -> str:
    if group not in ANGLE_GROUPS:
        raise PathError(f"unknown angle group {group!r}; expected one of {list(ANGLE_GROUPS)}")
    return config_prefix("pose", group)


def angle_key(group: str, basename: str) -> str:
    """An angle image's key. `basename` carries its own extension.

    **A NAME PATH, resolved like any other.** This docstring used to say the
    angle image was SHARED — handed to `store.shared_presign` rather than
    `store.presign`, because nothing wrote a catalog row for an angle image and
    resolving one would 404. Both halves are gone: `studio config sync` gives
    every angle image a node, and `shared_presign` / `shared_read` were deleted with
    the exception they existed for.
    """
    return join(angle_prefix(group), basename)
