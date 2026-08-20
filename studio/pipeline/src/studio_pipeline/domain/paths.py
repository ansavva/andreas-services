"""The ONE module that knows the bucket's shape.

Before this file the layout lived as ~20 inline f-strings spread across eight
scripts (`f"{owner}/{RUNS}/{run_id}"`, `f"{owner}/scenes/{scene_id}"`,
`f"{name}/{cfg['folder']}"` …). Moving a folder meant finding all of them. Now
every path in the pipeline is built here.

THE TWO TREES
-------------
A **character** is an identity record. A **project** is a unit of production.
They were the same folder once; they are not the same thing:

    characters/<name>/
        profile.yaml     the bible, including the described reference index
        reference/       generated character imagery, in purpose subfolders
        corpus/          collected images/videos of/for the character
        seed/            the founding real-world source photos
        archive/         retired material — never referenced unless asked for

    projects/<project>/
        project.json     name, description, the characters involved
        runs/            <run_id>/{request,prompt,result}.json + output/
        chains/          <slug>.json
        scenes/          <scene_id>/{scene.json, shots/, output/}
        movies/          <movie_id>/{movie.json, scenes/, output/}
        input/           the project working pool

    phrasebook/wording.yaml

    config/pose/{body,face}/*.png   shared pose + face-angle plates

`config/` is neither tree. It holds material that belongs to no character and no
project — the pose and head-angle plates a reference shoot passes to a model as a
framing guide. Its source of truth is the REPO (`studio/config/`), and
`dev-setup.sh` copies it out; S3 holds a copy because a model may only be handed
a presigned URL of an S3 object, never bytes from disk.

A project's material may involve several characters, so a character name is
never part of a production key — the run records which characters it used
(`request.json: characters[]`), and `character_of()` reads one back out of a
binding.

WHAT THESE STRINGS ARE, SINCE #303
----------------------------------
**Name paths, not S3 keys.** Every builder here returns a path the API resolves
through `GET /api/resolve` — the same string a person types and the same one
`adapters/store` takes. Nothing in this module knows a bucket name, a prefix or
a credential.

The bucket prefix is gone from the CLI entirely, and that is a removal rather
than a default: `STUDIO_S3_PREFIX` let this half of studio disagree with the
API about where the tree starts, and the API already owns that decision
(`STUDIO_MEDIA_ROOT_PREFIX`). One authority, not two that happen to agree.

CONVENTION — `*_prefix()` vs `*_key()`
--------------------------------------
Both return the same kind of string now, and the pair survives only because
twelve modules and every `SKILL.md` are written in these terms. Read `*_key()`
as "addresses one file" and `*_prefix()` as "addresses a folder"; the old
meaning — full key versus prefix-relative — died with the prefix. The bug the
split was invented for (`runs.py` and `scenes.py` disagreeing, producing
`media/media/…`) cannot recur, because there is no prefix to apply twice.

SHARED MATERIAL IS NOT IN THE CATALOG
-------------------------------------
`phrasebook_key`, `config_key` and `pose_key` are shared, not owned — they
belong to no character and no project, `catalog_seed.py` records neither of
them, and `dev-setup.sh` syncs the pose plates straight into the bucket. They
therefore have **no catalog node**, and resolving one would 404.

They are still not read with boto3. They go through the API's key-addressed
routes — `store.shared_presign` / `store.shared_read` over `GET /api/asset` —
which is the same authority reached a different way. See `adapters/store`.

LEGACY
------
`classify()` / `relocate()` map a key from the OLD layout (`media/<owner>/…`)
to its new home. They exist for `migrate_layout.py` and should be deleted once
no bucket anywhere still holds an old tree.
"""
from __future__ import annotations

import os
import re

from studio_pipeline.adapters import api, store

# ── names ───────────────────────────────────────────────────────────────────

CHARACTERS = "characters"
PROJECTS = "projects"

# Neither a character nor a project: shared, generic material kept in the repo
# and copied out to S3. `POSE_GROUPS` mirrors the character reference groups it
# guides, so a `body` slot asks for a `body` plate.
CONFIG = "config"
POSE_GROUPS = ("body", "face")

# Also neither tree: the per-model wording lists. Named beside `CONFIG` because
# the two share the property a caller cares about — they belong to no character
# and no project, which is why `catalog_seed.py` records neither of them.
PHRASEBOOK = "phrasebook"

# The four character pools. `reference` is the only one with structure inside
# it (purpose subfolders + the profile index); the rest keep arbitrary
# basenames, because renaming a source photo loses information for nothing.
CHAR_POOLS = ("reference", "corpus", "seed", "archive")

# The project subtrees the tools write to. `runs` is append-only history;
# `scenes` and `movies` are derived from it; `input` is the working pool. A
# project may hold other folders a person made — `favorites/` is one, left over
# from a feature that derived that destination rather than asking for it — and
# they are ordinary folders, browsable and copyable like any other.
PROJECT_DIRS = ("runs", "scenes", "movies", "chains", "input")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class PathError(Exception):
    pass


def check_slug(s: str, what: str = "name") -> str:
    """Character and project names share one rule — both become path segments."""
    if not s or not NAME_RE.match(s):
        raise PathError(f"invalid {what} {s!r}; use lowercase [a-z0-9_-] starting alphanumeric")
    return s


def _join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p not in (None, ""))


# ── characters ──────────────────────────────────────────────────────────────

def character_prefix(name: str) -> str:
    return _join(CHARACTERS, check_slug(name, "character name"))


def character_key(name: str, *parts: str) -> str:
    return _join(character_prefix(name), *parts)


def profile_key(name: str) -> str:
    return character_key(name, "profile.yaml")


def char_pool_prefix(name: str, pool: str) -> str:
    if pool not in CHAR_POOLS:
        raise PathError(f"unknown character pool {pool!r}; expected one of {list(CHAR_POOLS)}")
    return _join(character_prefix(name), pool)


def characters_root() -> str:
    return CHARACTERS + "/"


def character_of(key: str) -> str | None:
    """'characters/<c>/reference/…' -> '<c>'. Anything else -> None."""
    parts = key.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == CHARACTERS:
        return parts[1] or None
    return None


# ── projects ────────────────────────────────────────────────────────────────

def project_prefix(p: str) -> str:
    return _join(PROJECTS, check_slug(p, "project name"))


def project_key(p: str, *parts: str) -> str:
    return _join(project_prefix(p), *parts)


def project_json_key(p: str) -> str:
    return project_key(p, "project.json")


def project_dir_prefix(p: str, kind: str) -> str:
    if kind not in PROJECT_DIRS:
        raise PathError(f"unknown project dir {kind!r}; expected one of {list(PROJECT_DIRS)}")
    return _join(project_prefix(p), kind)


def projects_root() -> str:
    return PROJECTS + "/"


def project_of(key: str) -> str | None:
    parts = key.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == PROJECTS:
        return parts[1] or None
    return None


# runs ----------------------------------------------------------------------

def runs_prefix(p: str) -> str:
    return project_dir_prefix(p, "runs")


def run_prefix(p: str, run_id: str) -> str:
    return _join(runs_prefix(p), run_id)


def run_key(p: str, run_id: str, *parts: str) -> str:
    return _join(run_prefix(p, run_id), *parts)


# scenes --------------------------------------------------------------------

def scenes_prefix(p: str) -> str:
    return project_dir_prefix(p, "scenes")


def scene_prefix(p: str, scene_id: str) -> str:
    return _join(scenes_prefix(p), scene_id)


def scene_key(p: str, scene_id: str, *parts: str) -> str:
    return _join(scene_prefix(p, scene_id), *parts)


# movies --------------------------------------------------------------------

def movies_prefix(p: str) -> str:
    return project_dir_prefix(p, "movies")


def movie_prefix(p: str, movie_id: str) -> str:
    return _join(movies_prefix(p), movie_id)


def movie_key(p: str, movie_id: str, *parts: str) -> str:
    return _join(movie_prefix(p, movie_id), *parts)


# chains and the input pool --------------------------------------------------

def chains_prefix(p: str) -> str:
    return project_dir_prefix(p, "chains")


def chain_key(p: str, slug: str) -> str:
    return _join(chains_prefix(p), f"{slug}.json")


def input_prefix(p: str) -> str:
    return project_dir_prefix(p, "input")


def input_basename(p: str, n: int, ext: str) -> str:
    """`<project>_in_<n><ext>` — derived from the PROJECT, never a character.

    The first projects happen to be named after characters, so these agreed by
    coincidence; the first project named independently would have produced
    mismatched basenames if the prefix kept coming from the character.
    """
    return f"{p}_in_{n}{ext if ext.startswith('.') or not ext else '.' + ext}"


def input_key(p: str, n: int, ext: str) -> str:
    return _join(input_prefix(p), input_basename(p, n, ext))


# ── the phrasebook ──────────────────────────────────────────────────────────

def phrasebook_key() -> str:
    """SHARED. Read it with `store.shared_read` — it has no catalog node."""
    return _join(PHRASEBOOK, "wording.yaml")


# ── config ──────────────────────────────────────────────────────────────────

def config_root() -> str:
    return CONFIG + "/"


def config_prefix(*parts: str) -> str:
    return _join(CONFIG, *parts)


def config_key(*parts: str) -> str:
    """SHARED. See the module docstring — not resolvable, key-addressed."""
    return config_prefix(*parts)


def pose_prefix(group: str) -> str:
    if group not in POSE_GROUPS:
        raise PathError(f"unknown pose group {group!r}; expected one of {list(POSE_GROUPS)}")
    return config_prefix("pose", group)


def pose_key(group: str, basename: str) -> str:
    """A plate's key. `basename` carries its own extension.

    SHARED, so a shoot hands this to `store.shared_presign` and not to
    `store.presign`. The plates arrive by `dev-setup.sh`'s sync and no catalog
    row is ever written for them; resolving one would 404 and a reference shoot
    would silently lose its framing guide.
    """
    return _join(pose_prefix(group), basename)


# ── listing ─────────────────────────────────────────────────────────────────

def _folder_names(path: str) -> list[str]:
    """The immediate folder names under a path, natural-sorted.

    **A missing path is an empty list, not an error.** `GET /api/resolve` 404s
    on a library with no `characters/` yet, and the paginator this replaces
    answered the same question with zero `CommonPrefixes`. Callers ask "what is
    there" and none of them distinguish empty from absent, so neither does this.
    Only a 404 means empty — a 403 is a different fact and is left to surface.

    Folders only. The catalog returns files and folders together, where
    `list_objects_v2` with a delimiter returned them in separate fields — so the
    filter is now explicit where it used to be structural, and dropping it would
    list `project.json` as a project.
    """
    try:
        entries = store.children(path)
    except api.NotFound:
        return []
    names = [e["name"] for e in entries if e.get("kind") == "folder" and e.get("name")]
    return sorted(names, key=store.natural_key)


def list_characters() -> list[str]:
    return _folder_names(CHARACTERS)


def list_projects() -> list[str]:
    return _folder_names(PROJECTS)


def list_ids(prefix: str) -> list[str]:
    """Ids directly under a path — runs, scenes, movies.

    Ids sort chronologically because they start with a timestamp, so the plain
    sort is also 'oldest first'. Deliberately NOT the natural sort the folder
    listings use: a natural sort orders digit runs by numeric value, which for
    a timestamp is not the same question.
    """
    return sorted(_folder_names(prefix))


# ════════════════════════════════════════════════════════════════════════════
# LEGACY — the pre-restructure layout, and the map out of it.
# Everything below is migration-only and goes away with the old tree.
# ════════════════════════════════════════════════════════════════════════════

# The pre-restructure prefix. Only `classify()` below still needs to recognise
# it; the legacy key BUILDERS are gone, because nothing writes the old tree any
# more and keeping them would let something start again by accident.
LEGACY_PREFIX = "media/"


# ── the relocation map ──────────────────────────────────────────────────────
#
# One rule per old folder. Order matters: the first rule whose `match` accepts a
# key wins, so the narrow rules (which slice `input/` in two) come first.
#
# `dest` receives (owner, rest) where `rest` is everything after the folder, and
# returns a NEW-layout key. `owner` doubles as the character name and, for
# production folders, the project name — the two current owners become the two
# current projects, which is why every runref already recorded stays valid.

# Generated character imagery lived in the input pool to stay under the engine
# reference caps. It is reference material, and belongs with the character.
#
# A generic anatomy sheet used to be listed here too, which sent it to
# `reference/` — where it was indexed as identity and tagged `body`, so
# `--pick-tag body` could hand a model a stranger's sculpt as one of the
# character's own reference slots. Generic pose material is CONFIG: it lives in
# the repo and is copied to `config/pose/`, never into a character.
_TURNAROUND_RE = re.compile(r"^[a-z0-9_-]+_in_\d+\.[A-Za-z0-9]+$")
_SHEET_NAMES: set[str] = set()

# Owners that were never characters — production history with no identity.
NON_CHARACTER_OWNERS = {"misc"}


def _is_turnaround(basename: str) -> bool:
    return bool(_TURNAROUND_RE.match(basename)) or basename in _SHEET_NAMES


LEGACY_MAP: list[tuple[str, str, str]] = [
    # (rule id, old folder pattern for the report, human note)
    ("profile", "media/<c>/profile.yaml", "-> characters/<c>/profile.yaml"),
    ("reference", "media/<c>/reference/*", "-> characters/<c>/reference/*"),
    ("turnarounds", "media/<c>/input/<c>_in_*", "-> characters/<c>/reference/* (generated)"),
    ("uploads", "media/<c>/input/*", "-> characters/<c>/corpus/* (raw uploads)"),
    ("seed", "media/<c>/originals/*", "-> characters/<c>/seed/*"),
    ("corpus", "media/<c>/other/*", "-> characters/<c>/corpus/*"),
    ("archive", "media/<c>/trash/*", "-> characters/<c>/archive/*"),
    ("favorites", "media/<c>/favorites/*", "-> projects/<c>/favorites/*"),
    ("runs", "media/<c>/runs/*", "-> projects/<c>/runs/*"),
    ("shots", "media/<c>/scenes/<id>/parts/part-NN.*", "-> .../scenes/<id>/shots/shot-NN.*"),
    ("scenes", "media/<c>/scenes/*", "-> projects/<c>/scenes/*"),
    ("chains", "media/<c>/chains/*", "-> projects/<c>/chains/*"),
    ("phrasebook", "media/phrasebook/*", "-> phrasebook/*"),
]

_PART_RE = re.compile(r"^part-(\d+)(\.[A-Za-z0-9]+)$")


def classify(old_key: str) -> tuple[str, str] | None:
    """(rule_id, new_key) for an old-layout key, or None if it is not old-layout.

    Returning None means "nothing to do" — either the key is already in the new
    tree, or it is a folder marker. A key that IS old-layout but matches no rule
    raises, because silently leaving one behind is how a migration loses data.
    """
    if not old_key.startswith(LEGACY_PREFIX):
        return None
    rel = old_key[len(LEGACY_PREFIX):]
    if not rel or rel.endswith("/"):
        return None  # folder marker — dropped, not moved

    head, _, rest = rel.partition("/")
    if head == "phrasebook":
        return "phrasebook", _join("phrasebook", rest)
    if not rest:
        raise PathError(f"unmapped legacy key (no folder): {old_key!r}")

    owner = head
    folder, _, tail = rest.partition("/")

    if rest == "profile.yaml":
        return "profile", profile_key(owner)

    if folder == "reference":
        return "reference", character_key(owner, "reference", tail)

    if folder == "input":
        base = os.path.basename(tail)
        if _is_turnaround(base):
            return "turnarounds", character_key(owner, "reference", tail)
        return "uploads", character_key(owner, "corpus", tail)

    if folder == "originals":
        return "seed", character_key(owner, "seed", tail)
    if folder == "other":
        return "corpus", character_key(owner, "corpus", tail)
    if folder == "trash":
        return "archive", character_key(owner, "archive", tail)

    if folder == "favorites":
        return "favorites", project_key(owner, "favorites", tail)
    if folder == "runs":
        return "runs", project_key(owner, "runs", tail)
    if folder == "chains":
        return "chains", project_key(owner, "chains", tail)

    if folder == "scenes":
        sid, _, inner = tail.partition("/")
        if inner.startswith("parts/"):
            base = os.path.basename(inner)
            m = _PART_RE.match(base)
            if not m:
                raise PathError(f"unrecognised scene part name: {old_key!r}")
            return "shots", scene_key(owner, sid, "shots", f"shot-{m.group(1)}{m.group(2)}")
        return "scenes", scene_key(owner, sid, inner)

    raise PathError(f"unmapped legacy key: {old_key!r}")


def relocate(old_key: str) -> str | None:
    """The new home of an old key, or None when there is nothing to move.

    Idempotent by construction: a new-layout key does not start with `media/`,
    so `relocate(relocate(k))` is always None.
    """
    hit = classify(old_key)
    return hit[1] if hit else None
