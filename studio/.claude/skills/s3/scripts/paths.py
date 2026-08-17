"""paths.py — the ONE module that knows the bucket's shape.

Before this file the layout lived as ~20 inline f-strings spread across eight
scripts (`f"{owner}/{RUNS}/{run_id}"`, `f"{owner}/scenes/{scene_id}"`,
`f"{name}/{cfg['folder']}"` …). Moving a folder meant finding all of them. Now
every key in the harness is built here, and `s3_common.key()` remains the one
place a global prefix is applied.

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
        favorites/
        input/           the project working pool

    phrasebook/wording.yaml

A project's material may involve several characters, so a character name is
never part of a production key — the run records which characters it used
(`request.json: characters[]`), and `character_of()` reads one back out of a
binding.

CONVENTION — `*_prefix()` vs `*_key()`
--------------------------------------
`*_prefix()` returns a path **relative to the bucket prefix**, which is what
`s3_common.list_keys()` takes. `*_key()` returns a **full S3 key**, which is
what get/put/copy take. `runs.py` and `scenes.py` disagreed about this before;
mixing them silently produced `media/media/…`, so the split is now by name.

LEGACY
------
`classify()` / `relocate()` map a key from the OLD layout (`media/<owner>/…`)
to its new home. They exist for `migrate_layout.py` and should be deleted once
no bucket anywhere still holds an old tree.
"""
from __future__ import annotations

import os
import re

import s3_common as s3c

# ── names ───────────────────────────────────────────────────────────────────

CHARACTERS = "characters"
PROJECTS = "projects"

# The four character pools. `reference` is the only one with structure inside
# it (purpose subfolders + the profile index); the rest keep arbitrary
# basenames, because renaming a source photo loses information for nothing.
CHAR_POOLS = ("reference", "corpus", "seed", "archive")

# The project subtrees. `runs` is append-only history; `scenes` and `movies` are
# derived from it; `input` is the working pool; `favorites` is human curation.
PROJECT_DIRS = ("runs", "scenes", "movies", "chains", "favorites", "input")

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
    return s3c.key(_join(character_prefix(name), *parts))


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
    rel = _strip_prefix(key)
    parts = rel.split("/")
    if len(parts) >= 2 and parts[0] == CHARACTERS:
        return parts[1] or None
    return None


# ── projects ────────────────────────────────────────────────────────────────

def project_prefix(p: str) -> str:
    return _join(PROJECTS, check_slug(p, "project name"))


def project_key(p: str, *parts: str) -> str:
    return s3c.key(_join(project_prefix(p), *parts))


def project_json_key(p: str) -> str:
    return project_key(p, "project.json")


def project_dir_prefix(p: str, kind: str) -> str:
    if kind not in PROJECT_DIRS:
        raise PathError(f"unknown project dir {kind!r}; expected one of {list(PROJECT_DIRS)}")
    return _join(project_prefix(p), kind)


def projects_root() -> str:
    return PROJECTS + "/"


def project_of(key: str) -> str | None:
    rel = _strip_prefix(key)
    parts = rel.split("/")
    if len(parts) >= 2 and parts[0] == PROJECTS:
        return parts[1] or None
    return None


# runs ----------------------------------------------------------------------

def runs_prefix(p: str) -> str:
    return project_dir_prefix(p, "runs")


def run_prefix(p: str, run_id: str) -> str:
    return _join(runs_prefix(p), run_id)


def run_key(p: str, run_id: str, *parts: str) -> str:
    return s3c.key(_join(run_prefix(p, run_id), *parts))


# scenes --------------------------------------------------------------------

def scenes_prefix(p: str) -> str:
    return project_dir_prefix(p, "scenes")


def scene_prefix(p: str, scene_id: str) -> str:
    return _join(scenes_prefix(p), scene_id)


def scene_key(p: str, scene_id: str, *parts: str) -> str:
    return s3c.key(_join(scene_prefix(p, scene_id), *parts))


# movies --------------------------------------------------------------------

def movies_prefix(p: str) -> str:
    return project_dir_prefix(p, "movies")


def movie_prefix(p: str, movie_id: str) -> str:
    return _join(movies_prefix(p), movie_id)


def movie_key(p: str, movie_id: str, *parts: str) -> str:
    return s3c.key(_join(movie_prefix(p, movie_id), *parts))


# chains, favorites, the input pool ------------------------------------------

def chains_prefix(p: str) -> str:
    return project_dir_prefix(p, "chains")


def chain_key(p: str, slug: str) -> str:
    return s3c.key(_join(chains_prefix(p), f"{slug}.json"))


def favorites_prefix(p: str) -> str:
    return project_dir_prefix(p, "favorites")


def favorite_key(p: str, basename: str) -> str:
    return s3c.key(_join(favorites_prefix(p), basename))


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
    return s3c.key(_join(input_prefix(p), input_basename(p, n, ext)))


# ── the phrasebook ──────────────────────────────────────────────────────────

def phrasebook_key() -> str:
    return s3c.key("phrasebook/wording.yaml")


# ── listing ─────────────────────────────────────────────────────────────────

def _strip_prefix(key: str) -> str:
    pre = s3c.PREFIX
    return key[len(pre):] if pre and key.startswith(pre) else key


def _immediate_children(s3, prefix: str) -> list[str]:
    """The immediate 'folder' names under a media-relative prefix."""
    full = s3c.key(prefix.rstrip("/") + "/")
    out: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3c.BUCKET, Prefix=full, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []) or []:
            name = cp["Prefix"][len(full):].rstrip("/")
            if name:
                out.append(name)
    return sorted(out, key=s3c.natural_key)


def list_characters(s3) -> list[str]:
    return _immediate_children(s3, CHARACTERS)


def list_projects(s3) -> list[str]:
    return _immediate_children(s3, PROJECTS)


def list_ids(s3, prefix: str) -> list[str]:
    """Ids directly under a media-relative prefix — runs, scenes, movies.

    Ids sort chronologically because they start with a timestamp, so the plain
    sort is also 'oldest first'.
    """
    return sorted(_immediate_children(s3, prefix))


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
_TURNAROUND_RE = re.compile(r"^[a-z0-9_-]+_in_\d+\.[A-Za-z0-9]+$")
_SHEET_NAMES = {"body_positions.jpg"}

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
        return "phrasebook", s3c.key(_join("phrasebook", rest))
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
