"""`studio catalog migrate` — raise entity rows over a library already recorded.

**THIS IS NOT A SECOND INVENTORY.** The bucket is already in the catalog: the
one-shot that walked it and gave every folder and object a node ran, finished
and has been retired. What does not exist is the layer *above* those nodes — the
characters, projects, runs, scenes and movies that the nodes have always
spelled out as folder names and JSON documents and that nothing could query.
This command reads that layer out of the tree and writes it down as rows.

    Library    lib-…      the sharing unit                        (recorded)
     ├ Node    node-…     a folder or a file, with a parent       (recorded)
     ├ Character char-…   who a subject is                        <- written here
     ├ Project  proj-…    a unit of production                    <- written here
     ├ Run      run-…     one submission to a model               <- written here
     ├ Scene    scene-…   shots stitched into one take            <- written here
     └ Movie    movie-…   scenes cut into one piece               <- written here

So every phase below starts from the TABLE, not from a bucket listing. The
seed's `plan` deliberately took no DynamoDB client because it ran before the
table existed; here the table *is* the input and all four phases need it. S3 is
still opened, for two narrow jobs: reading the documents whose bytes carry the
structure (`profile.yaml`, `project.json`, `request.json`, …), and — in
`verify` — re-listing the bucket so the check is against the objects rather
than against the rows that claim them.

FOUR PHASES, EACH ITS OWN INVOCATION
------------------------------------
    plan     walk the catalog; report every entity it would create, every
             document it would parse, and every one it cannot.
             **UNPARSEABLE must be 0** — otherwise this exits non-zero and
             `apply` refuses.
    apply    create the entity rows. Each existing tree's top folder is
             ADOPTED as the entity's `root` — no folder is created, none is
             renamed, and none is reparented. Each `references:` entry becomes
             a `REF#` row; each run/scene/movie document becomes an envelope
             and STAYS WHERE IT IS as that envelope's payload blob.
    verify   read both sides back: every entity resolves, every folder it names
             exists and points back, every reference names a live node, every
             envelope's outputs exist as rows and as objects.
    reseat   optional, separate, later, and never automatic. See below.

Every phase is `--dry-run` unless `--apply`, and they are separate commands
because the ordering between them is the safety property — the same reason the
catalog seed split its three and the layout migrator before it split its five.
The journal (`local/migrations/<ts>.json`, git-ignored) records what each phase
did.

**IT COPIES NO BYTES, MOVES NO OBJECTS AND DELETES NOTHING.** Every key stays
exactly where it is; a run's `request.json` is still the same object at the same
key, and the envelope simply names its node. `reseat` is the one command in this
file that touches an object, it is a separate invocation, it refuses until
`verify` has passed, and it is the only reason the word `copy_object` appears
below.

EVERYTHING HERE IS A PURE FUNCTION OF THE CATALOG
-------------------------------------------------
Entity ids are derived, not drawn at random:

    char-<uuid5(NAMESPACE_URL, "studio://character/<root node id>")>

and the same shape for the other four, keyed on the node id of the folder the
entity adopts. Timestamps come from the documents, falling back to the node
rows. No phase reads a clock.

That is load-bearing and it is inherited straight from the catalog seed, whose
docstring made the argument: the phases each rebuild their picture from a fresh
read, so `apply` and `verify` can only agree with `plan` if the plan is
reproducible. Random ids would make a resumed `apply` create a *second*
character beside the half-written first one, because nothing would recognise
the rows already there.

**What changed is what the id is derived FROM, and the change matters.** The
seed derived a node id from `s3://<bucket>/<key>` because a key was the only
stable name an object had. An entity is derived from its root NODE ID instead —
never from its slug and never from a key. A slug is mutable by design now, and
somebody renaming a folder between `plan` and `apply` must not fork the
migration; a node id cannot be renamed. It stays an opaque id: nothing reads one
back to recover anything.

THE LEGACY LAYOUT LIVES HERE AND NOWHERE ELSE
---------------------------------------------
`domain/paths.py` used to be 334 lines that built `characters/<slug>/…` and
`projects/<slug>/…`. Every one of those builders is gone, because an entity
record names its own nodes. This module is the **only** code left that is
allowed to know the old shape, so the names it needs are declared once below,
under `LEGACY_*`, and nothing else in this file spells them inline.

Note what that knowledge now is: **folder and document NAMES, resolved through
the tree by name.** Not keys. `plan` finds a character by asking the library
root for its child called `characters` and listing that folder's children — one
query per level against rows that already exist — rather than by constructing
`characters/<slug>/profile.yaml` and hoping. A tree someone has already tidied
by hand therefore migrates correctly, and a tree that has drifted is reported
instead of silently half-read.

D5: THE SPARSE REEL KEY, AND THE FOLDER POLLUTION IT FIXES
----------------------------------------------------------
`by-recent` used to be hashed on `lib` and ranged on `created_at`, so every item
carrying both landed in it — every folder node, and every entity row this
command adds would have joined them. They were filtered out in memory *after*
consuming the reel's page cap. The index is re-keyed on a sparse `reel`
attribute, so `apply` stamps `reel = <lib>` onto exactly the file nodes whose
content type is an image or a video, and onto nothing else. Folders, documents
(`request.json` is a file node and is deliberately NOT in the reel), and every
entity row stay out of the enumeration entirely. That is why the entity records
below spell their timestamps `created` / `updated` rather than `created_at`:
belt and braces, and it makes the intent readable off the row.

The stamping is done with per-row conditional updates rather than in the entity
transactions. They are independent and idempotent, a half-finished stamping pass
is harmless, and a hundred-item transaction limit has no business deciding how
many images a library may hold.

RESEAT, AND WHY IT IS NOT PART OF `apply`
-----------------------------------------
The key scheme is `<owner_kind>/<owner_id>/<node_id>.<ext>` — it carries the
owning entity's id, so a bucket listing leaks no names and per-entity cost,
lifecycle and bulk delete all become one prefix. Prod's keys predate it. The
prefix is stamped once at creation and never re-derived, so a key that no longer
matches its node's owner is still perfectly correct — it is a pointer — it just
stops *looking* like it means anything.

`verify` reports that drift. `reseat --apply` rewrites it: server-side copy, row
update, delete of the old object. It is a separate invocation because it is the
only thing here that can lose data, it refuses to run until the journal records
a passing `verify`, and it is never reached by running `apply`.
"""
from __future__ import annotations

import collections
import contextlib
import datetime as dt
import json
import mimetypes
import os
import uuid

import click
import yaml

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die

JOURNAL_DIR = str(STUDIO_DIR / "local" / "migrations")

# Owned by nobody: no character, no project, no library. Read directly, recorded
# by no node, and therefore never an orphan and never collectable.
#
# `config/` comes from `paths.py`, which still names it — the pose plates are
# the last raw key in the pipeline and are documented there. `phrasebook/` is a
# **literal on purpose**: the phrasebook is `TERM#` rows now and `paths.py`
# stopped naming it, but every bucket written before that change still holds
# `phrasebook/wording.yaml`, and a prefix this list forgot is a prefix
# `catalog gc` would propose deleting. Legacy knowledge belongs in the migrator;
# this is the migrator.
SHARED_PREFIXES = (P.CONFIG + "/", "phrasebook/")

# ── the legacy layout: the ONLY declaration of it left in the package ───────
#
# Folder and document NAMES, not keys. Everything below is resolved by walking
# the tree from the library root, so nothing here asserts where an object lives.
LEGACY_CHARACTERS = "characters"   # the folder every character folder sits in
LEGACY_PROJECTS = "projects"       # ditto for projects
LEGACY_PROFILE = "profile.yaml"    # the bible, inside a character's folder
LEGACY_REFERENCE = "reference"     # what a `references:` entry's `file` is relative to
LEGACY_PROJECT_DOC = "project.json"
LEGACY_RUNS = "runs"
LEGACY_SCENES = "scenes"
LEGACY_MOVIES = "movies"
LEGACY_OUTPUT = "output"           # a run folder's outputs, when no result document names them
LEGACY_REQUEST = "request.json"
LEGACY_RESULT = "result.json"
LEGACY_PROMPT = "prompt.json"
LEGACY_SCENE_DOC = "scene.json"
LEGACY_MOVIE_DOC = "movie.json"

# `<kind>-<uuid4>` in the spec; `<kind>-<uuid5>` here, for the reason the
# docstring gives. The prefix is for a human reading a log — nothing parses one.
KIND_PREFIX = {"character": "char", "project": "proj", "run": "run",
               "scene": "scene", "movie": "movie"}

# The `pk` partition each entity kind gets.
PARTITION = {"character": "CHAR", "project": "PROJ", "run": "RUN",
             "scene": "SCENE", "movie": "MOVIE"}

# The two entity kinds that own bytes, and the key prefix each takes. Anything
# under no entity at all belongs to the library.
OWNER_PREFIX = {"character": "characters", "project": "projects"}
LIBRARY_PREFIX = "libraries"

# Reference `order` is gapped so inserting between two entries is one write and
# a reorder never touches its neighbours. The migration lays them out in the
# order the bible listed them, which is the order filename numbering encoded.
ORDER_GAP = 1000

# `TransactWriteItems` takes a hundred actions. A character with two hundred
# references would exceed it, so the reference rows are chunked; every other
# group here is bounded by the shape of the record and fits by construction.
REF_CHUNK = 24

# Enough of a list to judge it by. The journal holds more.
SHOWN = 10

# uuid5 over a URL is what NAMESPACE_URL is for. A node id is already globally
# unique — the seed derived it from `s3://<bucket>/<key>` — so an entity derived
# from one is unique across buckets without naming a bucket here.
_NAMESPACE = uuid.NAMESPACE_URL


# ── identity ────────────────────────────────────────────────────────────────

def entity_id(kind: str, root_node: str) -> str:
    """The id of the entity that adopts `root_node`.

    Derived from the node id and from nothing else — not the slug, not the key.
    See the module docstring: a slug is mutable by design, and a rename between
    `plan` and `apply` must not fork the migration.
    """
    return f"{KIND_PREFIX[kind]}-{uuid.uuid5(_NAMESPACE, f'studio://{kind}/{root_node}')}"


def content_type(name: str) -> str:
    """Guessed from the extension, not read back with a HEAD.

    Kept from the catalog seed, which measured the trade: every writer in this
    package sets `ContentType` from exactly this call, so guessing reproduces
    what is stored, at zero requests against a bucket with thousands of objects.
    `maintenance/dev_seed.py` is the other caller.
    """
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def in_the_reel(row: dict) -> bool:
    """Whether a node row qualifies for the sparse `by-recent` key (D5).

    A file, and an image or a video. **Not a folder** — that is the pollution
    the re-key fixes. **Not a document**: `request.json` is a file node and has
    no business in a reel of media. **Not an entity row**, which is not a node
    at all and never reaches this function.
    """
    return (row.get("kind") == "file"
            and str(row.get("content_type") or "").startswith(("image/", "video/")))


# ── reading the catalog ─────────────────────────────────────────────────────

def read_catalog(ddb, chosen: str | None = None) -> dict:
    """The whole table, indexed the four ways every phase below needs it.

    One scan, for the reason every maintenance command in this package scans: a
    GSI silently drops any row missing one of its key attributes, and a dropped
    row is exactly the corruption these phases are looking for. `by-recent` is
    now sparse *by design*, which makes reading the tree off an index wrong
    rather than merely risky.
    """
    libraries, nodes = {}, {}
    entities: set[tuple[str, str]] = set()
    for item in ddbc.scan(ddb):
        pk, sk = item.get("pk", ""), item.get("sk", "")
        partition = pk.split("#", 1)[0]
        if sk == "META" and partition == "LIB":
            libraries[pk.removeprefix("LIB#")] = item
        elif sk == "META" and partition == "NODE" and item.get("node_id"):
            nodes[item["node_id"]] = item
        elif partition in ("CHAR", "PROJ", "RUN", "SCENE", "MOVIE"):
            entities.add((pk, sk))
        elif partition == "LIB" and sk.startswith(("CHARSLUG#", "PROJSLUG#")):
            entities.add((pk, sk))

    if not libraries:
        die(f"no library in '{ddbc.table()}'. This migrates a library that is "
            "already recorded; there is nothing above an empty table to raise.")

    # **A table holds more than one library and always will.** Prod carries the
    # real one and `lib-smoke`, which `scripts/prod-seed-smoke.py` writes so the
    # post-deploy smoke test can sign in as an account that is a member of
    # exactly one library — that is the mechanism rather than a courtesy, so the
    # second library is permanent.
    #
    # This used to refuse outright while its own message claimed it migrated
    # "the one the bucket names". Nothing named a library: a bucket holds bytes,
    # and the table is the only thing that knows a library exists. So the choice
    # is the caller's, and it is demanded only when there is a choice to make.
    if chosen:
        if chosen not in libraries:
            die(f"no library {chosen!r} in '{ddbc.table()}'. It holds:\n"
                + "\n".join(f"       {lib}  ({row.get('name')})"
                            for lib, row in sorted(libraries.items())))
        lib = chosen
    elif len(libraries) > 1:
        die("this table holds more than one library — name the one to migrate "
            "with --library:\n"
            + "\n".join(f"       --library {lib}  ({row.get('name')})"
                        for lib, row in sorted(libraries.items())))
    else:
        lib = next(iter(libraries))
    root = libraries[lib].get("root_node")
    if root not in nodes:
        die(f"library {lib} names root node {root}, which has no row. The tree "
            "is broken below the layer this command writes; fix that first.")

    # Children by name, which is the only lookup the legacy layout needs. Every
    # node except the root has both, so a row missing either is already broken
    # and is left out rather than indexed under a guess.
    children: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for row in nodes.values():
        if row.get("parent_id") and row.get("name"):
            children[row["parent_id"]][row["name"]] = row

    # `blob_key -> node_id`. Legacy documents record S3 KEYS — a run's outputs,
    # its bindings, a movie's scene list — and this is what turns each of them
    # back into the node id the envelope must carry instead.
    by_blob = {row["blob_key"]: row["node_id"]
               for row in nodes.values() if row.get("blob_key")}

    # `name path -> node_id`, and it is the FALLBACK for a key `by_blob` cannot
    # answer — see `resolve_key`. Composed by walking down from the root rather
    # than read off a row, because `path` names ancestors by id.
    by_path: dict[str, str] = {}
    stack = [(root, "")]
    while stack:
        node_id, prefix = stack.pop()
        for name, row in children.get(node_id, {}).items():
            here = f"{prefix}{name}"
            by_path[here] = row["node_id"]
            stack.append((row["node_id"], here + "/"))

    return {"lib": lib, "root": root, "nodes": nodes, "children": children,
            "by_blob": by_blob, "by_path": by_path, "entities": entities,
            "name": libraries[lib].get("name") or "Studio"}


def resolve_key(cat: dict, value: str, by_path_hits: list[str]) -> str | None:
    """A key recorded in a legacy document -> the node id that holds it today.

    **Two lookups, and the second is the one that earns its keep.**

    `by_blob` is exact: the string in the document IS some node's `blob_key`,
    which is true of everything the catalog seed recorded. That is the answer
    wherever there is one.

    `by_path` is the fallback, and it is correct for the same reason the exact
    lookup usually works: before the catalog a name path and an S3 key were the
    same string. So a document naming `config/pose/face/<file>.png` is naming a
    *place in the tree*, and the node at that place today is the best available
    answer — often the only one, because a blob written since is keyed on ids
    and can never match the string a document recorded years ago.

    This is what the pose plates need. Every historical reference shoot bound a
    plate, the seed deliberately recorded no node for `config/`, and so every one
    of those bindings resolved to nothing — 28 of them across 29 runs in the
    first real migration, naming 16 distinct plates.

    **`studio config sync` recovers 26 of the 28, and 2 are unrecoverable.**
    That floor is worth stating, because the obvious reading of the sentence
    above is that the fallback fixes all of them and it does not. `config sync`
    uploads what is in `studio/config/` today, so a plate deleted from the repo
    can never get a node: `face/profile.png` and `body/three-quarter-right.png`
    went in the August 2026 plate rebuild, after the two runs that bound them,
    and neither survives in the bucket in any version — the rename that month
    was a copy, and a copy does not carry version history.

    Those two stay UNRESOLVED and their bindings are dropped, which is the right
    outcome rather than a gap to close. Re-pointing them at the plausible
    successor plate would put an unverifiable assertion into an envelope, where
    it would be indistinguishable from a binding that was really made. The run's
    `request.json` keeps the true key verbatim — `apply` rewrites no payload —
    so the answer to "what was this run shown" survives exactly where studio
    does not get to invent it.

    **It resolves by a MUTABLE handle and is therefore reported, never silent.**
    A name path is where something is now; a rename since the document was
    written would point this at a different file with the same name. That is
    still better than dropping the binding — the alternative is an envelope that
    claims a run was shown fewer images than it was — but it is an assumption,
    so every hit is counted and printed under `by path` rather than folded into
    the exact ones.
    """
    found = cat["by_blob"].get(value)
    if found is not None:
        return found
    found = cat["by_path"].get(value.strip("/"))
    if found is not None:
        by_path_hits.append(value)
    return found


def child(cat: dict, parent: str | None, name: str) -> dict | None:
    """The node called `name` inside `parent`, or None."""
    if parent is None:
        return None
    return cat["children"].get(parent, {}).get(name)


def descend(cat: dict, node_id: str | None, address: str) -> dict | None:
    """Walk a slash-joined chain of NAMES down from `node_id`.

    An address, resolved against the tree as it is — the same thing
    `GET /api/resolve?path=` does, and deliberately not a key being rebuilt.
    """
    row = cat["nodes"].get(node_id) if node_id else None
    for segment in [s for s in address.split("/") if s]:
        if row is None:
            return None
        row = child(cat, row.get("node_id"), segment)
    return row


def folders(cat: dict, parent: str | None) -> list[dict]:
    """`parent`'s folder children, name-ascending. The entity enumerations."""
    return sorted((row for row in cat["children"].get(parent, {}).values()
                   if row.get("kind") == "folder"),
                  key=lambda row: row["name"])


# ── reading the documents ───────────────────────────────────────────────────

def _read(s3, node: dict) -> bytes:
    key = node.get("blob_key")
    if not key:
        raise ValueError("the node has no blob_key")
    return s3.get_object(Bucket=s3c.bucket(), Key=key)["Body"].read()


def parse(s3, node: dict | None, what: str, unparseable: list[str],
          loader=json.loads) -> dict | None:
    """A document's contents, or None with a reason recorded.

    Every failure is COLLECTED rather than raised, for the reason the seed
    collected `unmapped`: a migration is fixed by looking at everything that is
    wrong at once, and a first-failure exit costs one round trip per mistake.
    """
    if node is None:
        unparseable.append(f"{what}: the document is not in the tree")
        return None
    try:
        doc = loader(_read(s3, node))
    except Exception as error:  # noqa: BLE001 — boto3, json and yaml all raise their own
        unparseable.append(f"{what}: {type(error).__name__}: {error}")
        return None
    if not isinstance(doc, dict):
        unparseable.append(f"{what}: parsed to {type(doc).__name__}, not a mapping")
        return None
    return doc


def _yaml(body: bytes):
    return yaml.safe_load(body)


# ── the plan ────────────────────────────────────────────────────────────────

def build_plan(s3, ddb, chosen: str | None = None) -> dict:
    """Every entity row this migration would write, parents before children.

    Read top-down, this is the legacy layout stated once: `characters/<slug>/`
    holds a bible, `projects/<slug>/` holds a manifest and three folders of
    dated subfolders, and each of those subfolders holds the documents that
    describe one submission to a model. That is the whole of what the old shape
    said, and after this command it is said by rows instead.
    """
    cat = read_catalog(ddb, chosen)
    lib, root = cat["lib"], cat["root"]

    # Two lists, and the split is deliberate.
    #
    #   unparseable — a document this cannot read at all. BLOCKS `apply`,
    #                 because an envelope built from a document nobody could
    #                 parse is a fiction, and the spec says the count must be 0.
    #   unresolved  — a document that parsed, naming something the tree does not
    #                 hold: a binding whose object has since been deleted, a
    #                 scene reference to a run that was tidied away. Reported
    #                 loudly and NOT blocking. Blocking on these would make the
    #                 migration unrunnable over exactly the history it exists to
    #                 preserve, and dropping them silently would lose the only
    #                 record that the reference was ever made.
    unparseable: list[str] = []
    unresolved: list[str] = []
    # Keys the exact lookup missed and the path lookup answered. Reported
    # separately, because a name path is a mutable handle — `resolve_key`.
    by_path_hits: list[str] = []

    characters = _plan_characters(s3, cat, unparseable, unresolved, by_path_hits)
    by_slug = {c["slug"]: c["id"] for c in characters}
    projects, runs, scenes, movies = _plan_projects(
        s3, cat, by_slug, unparseable, unresolved, by_path_hits)

    # D5. Every file node that qualifies and does not already carry the key.
    # A node that has one is skipped rather than rewritten: the API stamps it on
    # every upload now, and re-stamping would be a write per object for no
    # change.
    reel = sorted(row["node_id"] for row in cat["nodes"].values()
                  if in_the_reel(row) and not row.get("reel"))
    # And the pollution, counted so the report can show what the sparse key
    # excludes rather than merely asserting it.
    polluted = sum(1 for row in cat["nodes"].values()
                   if row.get("reel") and not in_the_reel(row))

    return {"lib": lib, "root": root, "library_name": cat["name"], "catalog": cat,
            "characters": characters, "projects": projects, "runs": runs,
            "scenes": scenes, "movies": movies, "reel": reel,
            "polluted": polluted, "unparseable": unparseable,
            "unresolved": unresolved, "by_path": by_path_hits}


def _plan_characters(s3, cat, unparseable, unresolved, by_path_hits) -> list[dict]:
    """One record per folder under `characters/`, plus its reference rows."""
    out = []
    tree = child(cat, cat["root"], LEGACY_CHARACTERS)
    for folder in folders(cat, tree["node_id"] if tree else None):
        slug, root = folder["name"], folder["node_id"]
        where = f"{LEGACY_CHARACTERS}/{slug}"
        try:
            P.check_slug(slug, "character slug")
        except P.PathError as error:
            # A slug is an attribute now, so this is a legibility rule rather
            # than a filesystem one — but it is also a KEY, in the claim item,
            # and a claim nobody can type is a character nobody can address.
            unparseable.append(f"{where}: {error}")
            continue

        doc = parse(s3, child(cat, root, LEGACY_PROFILE),
                    f"{where}/{LEGACY_PROFILE}", unparseable, _yaml)
        if doc is None:
            continue

        # The three fields promoted out of the bible onto the record, and the
        # two that become rows. Everything left is `profile`, stored as nested
        # maps and validated by the API from here on.
        profile = {k: v for k, v in doc.items()
                   if k not in ("name", "display_name", "fictional",
                                "schema_version", "references", "default_set")}

        refs, seen = [], set()
        for position, entry in enumerate(doc.get("references") or []):
            ref = _plan_reference(cat, root, where, position, entry,
                                  seen, unparseable, unresolved, by_path_hits)
            if ref is not None:
                refs.append(ref)

        default_set = []
        for entry in doc.get("default_set") or []:
            node = descend(cat, root, f"{LEGACY_REFERENCE}/{entry}")
            if node is None:
                unresolved.append(f"{where}: default_set names {entry!r}, "
                                  "which is not in the tree")
                continue
            default_set.append(node["node_id"])

        born = folder.get("created_at")
        out.append({
            "kind": "character", "id": entity_id("character", root), "lib": cat["lib"],
            "slug": slug, "root": root, "where": where,
            "display_name": doc.get("display_name") or slug,
            "fictional": bool(doc.get("fictional", True)),
            "schema_version": doc.get("schema_version"),
            "profile": profile,
            # The bible already expressed this choice, so it is carried rather
            # than invented: the card image is the first image of the set a
            # generation is shown, falling back to the first reference at all.
            "hero": (default_set or [r["node"] for r in refs] or [None])[0],
            "default_set": default_set,
            "created": born, "updated": folder.get("updated_at") or born,
            "refs": refs,
        })
    return out


def _plan_reference(cat, root, where, position, entry, seen,
                    unparseable, unresolved, by_path_hits) -> dict | None:
    """One `REF#` row out of one `references:` entry.

    **This is the row that kills filename magic.** `<slug>_<group>_<n>.png`
    encoded three things in a basename — whose it is, what it is for, and where
    it sits in the order — and the bible then keyed its descriptions on that
    same basename, which is why the two went out of step every time
    `curate renumber` ran. Here identity is the node id, `group` is an
    attribute, `order` is an attribute, and the file may be called anything.

    The group comes off the entry's own `file` path (`face/…` was a `face`
    reference), because that is where the old shape actually recorded it.
    """
    if not isinstance(entry, dict) or not entry.get("file"):
        unparseable.append(f"{where}: references[{position}] has no `file`")
        return None
    relative = str(entry["file"]).strip("/")
    node = descend(cat, root, f"{LEGACY_REFERENCE}/{relative}")
    if node is None:
        unresolved.append(f"{where}: references[{position}] names {relative!r}, "
                          "which is not in the tree")
        return None
    if node["node_id"] in seen:
        # `REF#<node_id>` is a key, so the same image listed twice is one row.
        # The duplicate is reported rather than dropped silently: it means the
        # bible disagreed with itself about a description.
        unresolved.append(f"{where}: references[{position}] repeats "
                          f"{relative!r}; the first entry wins")
        return None
    seen.add(node["node_id"])
    group = entry.get("group") or (relative.split("/")[0] if "/" in relative else "face")
    tags = entry.get("tags") or []
    return {"node": node["node_id"], "group": str(group),
            "order": (position + 1) * ORDER_GAP,
            "description": entry.get("description"),
            "tags": [str(t) for t in tags] if isinstance(tags, list) else [str(tags)],
            "created": node.get("created_at")}


def _plan_projects(s3, cat, by_slug, unparseable, unresolved, by_path_hits):
    """A record per folder under `projects/`, and the three tiers inside each."""
    projects, runs, scenes, movies = [], [], [], []
    tree = child(cat, cat["root"], LEGACY_PROJECTS)
    for folder in folders(cat, tree["node_id"] if tree else None):
        slug, root = folder["name"], folder["node_id"]
        where = f"{LEGACY_PROJECTS}/{slug}"
        try:
            P.check_slug(slug, "project slug")
        except P.PathError as error:
            unparseable.append(f"{where}: {error}")
            continue

        doc = parse(s3, child(cat, root, LEGACY_PROJECT_DOC),
                    f"{where}/{LEGACY_PROJECT_DOC}", unparseable) or {}

        proj = entity_id("project", root)
        involved = []
        for name in doc.get("characters") or []:
            if name in by_slug:
                involved.append(by_slug[name])
            else:
                unresolved.append(f"{where}: names character {name!r}, which "
                                  "has no folder under characters/")

        mine_runs = _plan_runs(s3, cat, proj, root, where, by_slug,
                               unparseable, unresolved, by_path_hits)
        by_run_slug = {r["slug"]: r["id"] for r in mine_runs}
        mine_scenes = _plan_scenes(s3, cat, proj, root, where, by_run_slug,
                                   unparseable, unresolved, by_path_hits)
        by_scene_slug = {s["slug"]: s["id"] for s in mine_scenes}
        mine_movies = _plan_movies(s3, cat, proj, root, where, by_scene_slug,
                                   unparseable, unresolved, by_path_hits)
        runs += mine_runs
        scenes += mine_scenes
        movies += mine_movies

        born = doc.get("created") or folder.get("created_at")
        projects.append({
            "kind": "project", "id": proj, "lib": cat["lib"], "slug": slug,
            "root": root, "where": where,
            "title": doc.get("title") or doc.get("name") or slug,
            "description": doc.get("description"),
            # Every character a run in this project used is involved in it, even
            # if the manifest never said so. The manifest was hand-maintained;
            # the runs are the evidence.
            "characters": sorted(set(involved)
                                 | {c for r in mine_runs for c in r["characters"]}),
            # Maintained from here on rather than scanned, so the migration is
            # what seeds them.
            "counts": {"runs": len(mine_runs), "scenes": len(mine_scenes),
                       "movies": len(mine_movies)},
            # Deliberately unset. A project's card image is a choice, the old
            # shape never recorded one, and picking the newest output for
            # somebody is the kind of invention a migration should not make.
            "hero": None,
            "created": born, "updated": folder.get("updated_at") or born,
        })
    return projects, runs, scenes, movies


def _plan_runs(s3, cat, proj, project_root, project_where, by_slug,
               unparseable, unresolved, by_path_hits) -> list[dict]:
    """One envelope per folder under a project's `runs/`.

    **The envelope is studio's; the payload is the provider's.** `request.json`
    and `result.json` are read for the fields studio owns and validates — status,
    model, engine, kind, timings, prediction id, which characters were used,
    which node each binding pointed at, which nodes came back — and are then
    LEFT WHERE THEY ARE as payload blobs the record names and never decodes.
    That is the present rule ("do not decode `request.json`") moved to where it
    is actually true, rather than weakened.
    """
    out = []
    tree = child(cat, project_root, LEGACY_RUNS)
    for folder in folders(cat, tree["node_id"] if tree else None):
        slug, node = folder["name"], folder["node_id"]
        where = f"{project_where}/{LEGACY_RUNS}/{slug}"
        request_node = child(cat, node, LEGACY_REQUEST)
        request = parse(s3, request_node, f"{where}/{LEGACY_REQUEST}",
                        unparseable)
        if request is None:
            continue
        result_node = child(cat, node, LEGACY_RESULT)
        result = ({} if result_node is None
                  else parse(s3, result_node, f"{where}/{LEGACY_RESULT}",
                             unparseable))
        if result is None:
            continue
        prompt_node = child(cat, node, LEGACY_PROMPT)

        bindings = {}
        for name, values in (request.get("bindings") or {}).items():
            listed = values if isinstance(values, list) else [values]
            ids = []
            for value in listed:
                found = resolve_key(cat, str(value), by_path_hits)
                if found is None:
                    unresolved.append(f"{where}: binding {name!r} names "
                                      f"{value!r}, which no node claims")
                    continue
                ids.append(found)
            bindings[name] = ids

        outputs = _run_outputs(cat, node, where, result, unresolved)

        characters = sorted({by_slug[name] for name in request.get("characters") or []
                             if name in by_slug})
        for name in request.get("characters") or []:
            if name not in by_slug:
                unresolved.append(f"{where}: used character {name!r}, which has "
                                  "no folder under characters/")

        born = request.get("created_at") or folder.get("created_at")
        lineage = request.get("lineage") or {}
        out.append({
            "kind": "run", "id": entity_id("run", node), "lib": cat["lib"],
            "project": proj, "slug": slug, "folder": node, "where": where,
            "status": _status(result, outputs),
            "run_kind": request.get("kind"),
            "engine": request.get("engine"), "model": request.get("model"),
            "prediction_id": result.get("prediction_id"),
            "created": born,
            "submitted": request.get("submitted_at") or request.get("submitted"),
            "completed": result.get("completed_at") or result.get("completed"),
            "bindings": bindings, "characters": characters,
            "outputs": outputs,
            "lineage": {"from_run": lineage.get("from_run"),
                        "from_output": cat["by_blob"].get(
                            str(lineage.get("from_output") or ""))},
            "cost": result.get("cost"),
            "error": result.get("error"),
            "payload": {
                "request": request_node["node_id"],
                "response": result_node["node_id"] if result_node else None,
                "prompt": prompt_node["node_id"] if prompt_node else None,
            },
        })
    return out


def _run_outputs(cat, node, where, result, unresolved) -> list[str]:
    """The nodes a run produced, from the result document or from `output/`.

    The document is authoritative when it exists, because it records the order
    the provider returned them in. When it does not — an interrupted run wrote
    no result — the run's `output/` folder is listed instead. Inventing nothing
    would be tidier and would strand every byte of an interrupted run outside
    the envelope that is supposed to name it.
    """
    listed = result.get("outputs")
    if listed:
        found = []
        for key in listed:
            node_id = cat["by_blob"].get(str(key))
            if node_id is None:
                unresolved.append(f"{where}: output {key!r} is claimed by no node")
                continue
            found.append(node_id)
        return found
    folder = child(cat, node, LEGACY_OUTPUT)
    if folder is None:
        return []
    return [row["node_id"]
            for row in sorted(cat["children"].get(folder["node_id"], {}).values(),
                              key=lambda r: r["name"])
            if row.get("kind") == "file"]


def _status(result: dict, outputs: list[str]) -> str:
    """One of the five the record allows.

    A legacy result document carried whatever the provider's vocabulary was, so
    an unrecognised value is mapped on the evidence rather than copied through:
    a run with outputs succeeded whatever it called itself, and a run with a
    result document, no outputs and no error never finished.
    """
    status = str(result.get("status") or "").lower()
    if status in ("pending", "running", "succeeded", "failed", "cancelled"):
        return status
    if status in ("succeeded", "success", "complete", "completed") or outputs:
        return "succeeded"
    if result.get("error") or status in ("failed", "error", "canceled"):
        return "failed"
    return "pending"


def _plan_scenes(s3, cat, proj, project_root, project_where, by_run_slug,
                 unparseable, unresolved, by_path_hits) -> list[dict]:
    """One envelope per folder under `scenes/`, with a `SHOT#` row per shot.

    **A scene document's shape is the least settled thing this command reads** —
    `parts` became `shots` and `part_key` became `shot_key` in an earlier
    rename, and the older spellings are still on disk. So the envelope carries
    what studio can name and validate, the shots become rows in plan order, and
    everything else stays in the document, which the record names and nobody
    decodes. That is principle 4 applied to a format studio itself changed.
    """
    out = []
    tree = child(cat, project_root, LEGACY_SCENES)
    for folder in folders(cat, tree["node_id"] if tree else None):
        slug, node = folder["name"], folder["node_id"]
        where = f"{project_where}/{LEGACY_SCENES}/{slug}"
        document = child(cat, node, LEGACY_SCENE_DOC)
        doc = parse(s3, document, f"{where}/{LEGACY_SCENE_DOC}", unparseable)
        if doc is None:
            continue

        shots = []
        for position, shot in enumerate(doc.get("shots") or doc.get("parts") or []):
            if not isinstance(shot, dict):
                unresolved.append(f"{where}: shots[{position}] is not a mapping")
                continue
            run_slug = shot.get("run") or shot.get("run_id")
            if run_slug and run_slug not in by_run_slug:
                unresolved.append(f"{where}: shots[{position}] names run "
                                  f"{run_slug!r}, which has no folder")
            panel = shot.get("panel") or shot.get("shot_key") or shot.get("part_key")
            shots.append({
                # Position IS the identity of a legacy shot: the old plan was a
                # list and carried nothing else to key one on.
                "shot_id": f"{position + 1:04d}",
                "order": (position + 1) * ORDER_GAP,
                "prompt": shot.get("prompt"),
                "run": by_run_slug.get(str(run_slug)) if run_slug else None,
                "panel": cat["by_blob"].get(str(panel)) if panel else None,
            })

        born = doc.get("created_at") or doc.get("created") or folder.get("created_at")
        cut = doc.get("output") or doc.get("cut") or doc.get("output_key")
        out.append({
            "kind": "scene", "id": entity_id("scene", node), "lib": cat["lib"],
            "project": proj, "slug": slug, "folder": node, "where": where,
            "title": doc.get("title") or slug,
            "status": "succeeded" if cut else "pending",
            "output": cat["by_blob"].get(str(cut)) if cut else None,
            "document": document["node_id"],
            "created": born, "updated": folder.get("updated_at") or born,
            "shots": shots,
        })
    return out


def _plan_movies(s3, cat, proj, project_root, project_where, by_scene_slug,
                 unparseable, unresolved, by_path_hits) -> list[dict]:
    """One envelope per folder under `movies/` — the tier above a scene."""
    out = []
    tree = child(cat, project_root, LEGACY_MOVIES)
    for folder in folders(cat, tree["node_id"] if tree else None):
        slug, node = folder["name"], folder["node_id"]
        where = f"{project_where}/{LEGACY_MOVIES}/{slug}"
        document = child(cat, node, LEGACY_MOVIE_DOC)
        doc = parse(s3, document, f"{where}/{LEGACY_MOVIE_DOC}", unparseable)
        if doc is None:
            continue

        # A movie manifest listed its scenes as SCENEREFS *and* as S3 keys,
        # interchangeably, so both are tried and whichever answers wins.
        listed = []
        for position, entry in enumerate(doc.get("scenes") or []):
            name = entry.get("scene") if isinstance(entry, dict) else entry
            found = by_scene_slug.get(str(name))
            if found is None:
                unresolved.append(f"{where}: scenes[{position}] names {name!r}, "
                                  "which is not a scene in this project")
                continue
            listed.append(found)

        born = doc.get("created_at") or doc.get("created") or folder.get("created_at")
        cut = doc.get("output") or doc.get("cut") or doc.get("output_key")
        out.append({
            "kind": "movie", "id": entity_id("movie", node), "lib": cat["lib"],
            "project": proj, "slug": slug, "folder": node, "where": where,
            "title": doc.get("title") or slug,
            "status": "succeeded" if cut else "pending",
            "output": cat["by_blob"].get(str(cut)) if cut else None,
            "document": document["node_id"],
            "scenes": listed,
            "created": born, "updated": folder.get("updated_at") or born,
        })
    return out


# ── the items ───────────────────────────────────────────────────────────────
#
# One function per entity, each returning the transaction groups that create it.
# A group is atomic; the groups are ordered so a resumed `apply` finds the work
# it has already done and reports it as skipped rather than doing it twice.


def adopt(node_id: str, entity: str) -> dict:
    """Point a folder node back at the entity that adopts it.

    **The reverse pointer, and the reason `apply` creates no folder.** The
    forward pointer is `root` on the record; this is the one attribute in the
    other direction, and it is what lets a listing draw a character card instead
    of a folder icon. Written once, never changed.

    An `Update` rather than a `Put`: the node row already exists and everything
    else on it — its name, its parent, its `path`, its stamps — belongs to the
    tree and is none of this command's business.
    """
    return {"Update": {
        "TableName": ddbc.table(),
        "Key": ddbc.to_item({"pk": f"NODE#{node_id}", "sk": "META"}),
        "UpdateExpression": "SET #entity = :entity",
        "ExpressionAttributeNames": {"#entity": "entity"},
        "ExpressionAttributeValues": ddbc.to_item({":entity": entity}),
        "ConditionExpression": "attribute_exists(pk)",
    }}


# **`id` IS AN ATTRIBUTE, NOT ONLY A KEY, AND LEAVING IT OUT BROKE PROD.**
#
# Every record below spells its own id twice — once inside `pk`, once as `id` —
# and the redundancy is the contract rather than an oversight. The API's
# unmarshaller (`services/catalog.py::_entity`) *drops* `pk` and `sk` on the way
# out and never derives an id from either, so a row carrying the id only in its
# key reads back as a record with no id. `entities_in` then does
# `found[record["id"]]` and every listing 500s.
#
# That is not hypothetical: the first prod migration wrote 32 entity rows this
# way, `verify` passed on all of them, and `GET /api/characters` and
# `GET /api/projects` returned 500 until the rows were backfilled. `verify` now
# checks the attribute for that reason — see `phase_verify`.
#
# The same applies to the three listing rows, which additionally need `created`:
# `routes/runs.py` sorts and `--since`-filters on it, so a listing row without
# one sorts as the empty string and disappears from every filtered view.
def character_groups(char: dict) -> list[list[dict]]:
    """The record, the slug claim, the root pointer, then the reference rows.

    The first group is one transaction for the reason a node is one transaction:
    a record without its claim is unlistable and its slug is unprotected, and a
    claim without its record points at nothing. Either all of it exists or none
    of it does.
    """
    record = {
        "pk": f"CHAR#{char['id']}", "sk": "META", "id": char["id"],
        "lib": char["lib"],
        "slug": char["slug"], "display_name": char["display_name"],
        "fictional": char["fictional"], "schema_version": char["schema_version"],
        "rev": 1, "created": char["created"], "updated": char["updated"],
        "root": char["root"], "hero": char["hero"],
        "default_set": char["default_set"], "profile": char["profile"],
    }
    claim = {"pk": f"LIB#{char['lib']}", "sk": f"CHARSLUG#{char['slug']}",
             "entity": char["id"], "created": char["created"]}
    groups = [[ddbc.put(record), ddbc.put(claim), adopt(char["root"], char["id"])]]
    refs = [ddbc.put({"pk": f"CHAR#{char['id']}", "sk": f"REF#{ref['node']}",
                      "lib": char["lib"], "group": ref["group"],
                      "order": ref["order"], "description": ref["description"],
                      "tags": ref["tags"], "created": ref["created"]})
            for ref in char["refs"]]
    groups += [refs[i:i + REF_CHUNK] for i in range(0, len(refs), REF_CHUNK)]
    return groups


def project_groups(proj: dict) -> list[list[dict]]:
    record = {
        "pk": f"PROJ#{proj['id']}", "sk": "META", "id": proj["id"],
        "lib": proj["lib"],
        "slug": proj["slug"], "title": proj["title"],
        "description": proj["description"], "rev": 1,
        "created": proj["created"], "updated": proj["updated"],
        "root": proj["root"], "hero": proj["hero"], "counts": proj["counts"],
    }
    claim = {"pk": f"LIB#{proj['lib']}", "sk": f"PROJSLUG#{proj['slug']}",
             "entity": proj["id"], "created": proj["created"]}
    # Involvement is rows and not a list on the record, which is the whole
    # reason "which projects involve this character" becomes answerable: read
    # backwards on `by-sk` it is one query, and a character delete can find what
    # points at it.
    links = [ddbc.put({"pk": f"PROJ#{proj['id']}", "sk": f"CHAR#{char}",
                       "lib": proj["lib"], "created": proj["created"]})
             for char in proj["characters"]]
    return [[ddbc.put(record), ddbc.put(claim),
             adopt(proj["root"], proj["id"])] + links]


def run_updated(run: dict) -> str:
    """A run's `updated`, read off the run rather than off a clock.

    The API stamps `updated` at creation and moves it forward on each
    transition; a run being migrated has already made all of its, so the last
    timestamp its document carries IS its `updated`. Falling back through
    completed -> submitted -> created keeps a run that never finished honest
    instead of dating it to the migration.
    """
    return run["completed"] or run["submitted"] or run["created"]


def run_groups(run: dict) -> list[list[dict]]:
    """The envelope, the project listing row, and one usage link per character.

    The listing row IS a small projection and that is a deliberate exception to
    the rule the slug claims follow: a run is immutable once it completes, so
    there is nothing to keep in step, and the runs screen would otherwise need a
    `BatchGetItem` over hundreds of envelopes to draw a grid.
    """
    record = {
        "pk": f"RUN#{run['id']}", "sk": "META", "id": run["id"],
        "lib": run["lib"],
        "project": run["project"], "slug": run["slug"], "status": run["status"],
        "kind": run["run_kind"], "engine": run["engine"], "model": run["model"],
        "prediction_id": run["prediction_id"], "rev": 1,
        "created": run["created"], "updated": run_updated(run),
        "submitted": run["submitted"], "completed": run["completed"],
        "bindings": run["bindings"], "characters": run["characters"],
        "folder": run["folder"], "outputs": run["outputs"],
        "lineage": run["lineage"], "cost": run["cost"], "error": run["error"],
        "payload": run["payload"],
    }
    listing = {"pk": f"PROJ#{run['project']}",
               "sk": f"RUN#{run['created']}#{run['id']}", "id": run["id"],
               "lib": run["lib"], "created": run["created"],
               "status": run["status"], "model": run["model"],
               "kind": run["run_kind"],
               "thumb": run["outputs"][0] if run["outputs"] else None}
    links = [ddbc.put({"pk": f"RUN#{run['id']}", "sk": f"CHAR#{char}",
                       "lib": run["lib"], "created": run["created"]})
             for char in run["characters"]]
    # The run's folder is adopted like any other entity root, so a listing can
    # draw a run card and `GET /api/nodes/<id>/owner` can walk up to it.
    return [[ddbc.put(record), ddbc.put(listing),
             adopt(run["folder"], run["id"])] + links]


def scene_groups(scene: dict) -> list[list[dict]]:
    record = {
        "pk": f"SCENE#{scene['id']}", "sk": "META", "id": scene["id"],
        "lib": scene["lib"],
        "project": scene["project"], "slug": scene["slug"],
        "title": scene["title"], "status": scene["status"],
        "folder": scene["folder"], "output": scene["output"],
        "payload": {"document": scene["document"]}, "rev": 1,
        "created": scene["created"], "updated": scene["updated"],
    }
    listing = {"pk": f"PROJ#{scene['project']}",
               "sk": f"SCENE#{scene['created']}#{scene['id']}",
               "id": scene["id"], "created": scene["created"],
               "lib": scene["lib"], "status": scene["status"],
               "title": scene["title"], "thumb": scene["output"]}
    shots = [ddbc.put({"pk": f"SCENE#{scene['id']}", "sk": f"SHOT#{shot['shot_id']}",
                       "lib": scene["lib"], "order": shot["order"],
                       "prompt": shot["prompt"], "run": shot["run"],
                       "panel": shot["panel"], "created": scene["created"]})
             for shot in scene["shots"]]
    first = [ddbc.put(record), ddbc.put(listing), adopt(scene["folder"], scene["id"])]
    groups = [first + shots[:REF_CHUNK]]
    rest = shots[REF_CHUNK:]
    groups += [rest[i:i + REF_CHUNK] for i in range(0, len(rest), REF_CHUNK)]
    return groups


def movie_groups(movie: dict) -> list[list[dict]]:
    record = {
        "pk": f"MOVIE#{movie['id']}", "sk": "META", "id": movie["id"],
        "lib": movie["lib"],
        "project": movie["project"], "slug": movie["slug"],
        "title": movie["title"], "status": movie["status"],
        "folder": movie["folder"], "output": movie["output"],
        "scenes": movie["scenes"], "payload": {"document": movie["document"]},
        "rev": 1,
        "created": movie["created"], "updated": movie["updated"],
    }
    listing = {"pk": f"PROJ#{movie['project']}",
               "sk": f"MOVIE#{movie['created']}#{movie['id']}",
               "id": movie["id"], "created": movie["created"],
               "lib": movie["lib"], "status": movie["status"],
               "title": movie["title"], "thumb": movie["output"]}
    return [[ddbc.put(record), ddbc.put(listing),
             adopt(movie["folder"], movie["id"])]]


GROUPS = {"character": character_groups, "project": project_groups,
          "run": run_groups, "scene": scene_groups, "movie": movie_groups}


# ── apply ───────────────────────────────────────────────────────────────────

def stamp_reel(ddb, node_id: str, lib: str) -> bool:
    """Write the sparse `by-recent` key onto one file node. False if it had one.

    Conditional on the attribute being absent, so the pass is resumable and a
    second run costs a refused condition per row rather than a rewrite. Not part
    of any entity transaction: these are independent of each other and of every
    record, and a partially stamped library is a library whose reel is short,
    not one that is wrong.
    """
    try:
        ddb.update_item(
            TableName=ddbc.table(),
            Key=ddbc.to_item({"pk": f"NODE#{node_id}", "sk": "META"}),
            UpdateExpression="SET #reel = :reel",
            ExpressionAttributeNames={"#reel": "reel"},
            ExpressionAttributeValues=ddbc.to_item({":reel": lib}),
            ConditionExpression="attribute_exists(pk) AND attribute_not_exists(#reel)",
        )
    except ddb.exceptions.ConditionalCheckFailedException:
        return False
    return True


def backfill(ddb, doc: dict, apply: bool) -> list[str]:
    """Add the attributes `doc` carries and the stored row lacks. Names them.

    **Strictly additive, and that is what makes it safe to run over a library
    somebody has been using.** A row already there may have been edited through
    the app since the migration — a renamed slug, a new hero, a bumped `rev` —
    so this never overwrites a value that is present. Every attribute it does
    write is guarded by its own `attribute_not_exists`, so the whole update is
    refused rather than half-applied if a concurrent write got there first.

    It exists because `apply` skipped an entity whose head row was present,
    which is right when the row is complete and wrong when an older version of
    this file wrote an incomplete one. The first prod migration wrote 32 of
    those; re-running `apply` counted them "already there" and repaired nothing.
    """
    got = ddb.get_item(TableName=ddbc.table(),
                       Key=ddbc.to_item({"pk": doc["pk"], "sk": doc["sk"]}))
    if "Item" not in got:
        return []
    have = ddbc.from_item(got["Item"])
    # `None` is dropped by `to_item`, so an absent attribute whose value would
    # be `None` is already what the schema means and is not a gap to close.
    names = sorted(key for key, value in doc.items()
                   if key not in ("pk", "sk") and key not in have
                   and value is not None)
    if not names or not apply:
        return names

    ddb.update_item(
        TableName=ddbc.table(),
        Key=ddbc.to_item({"pk": doc["pk"], "sk": doc["sk"]}),
        UpdateExpression="SET " + ", ".join(f"#a{i} = :a{i}"
                                            for i in range(len(names))),
        ExpressionAttributeNames={f"#a{i}": key for i, key in enumerate(names)},
        ExpressionAttributeValues=ddbc.to_item(
            {f":a{i}": doc[key] for i, key in enumerate(names)}),
        ConditionExpression=" AND ".join(
            ["attribute_exists(pk)"]
            + [f"attribute_not_exists(#a{i})" for i in range(len(names))]),
    )
    return names


def phase_apply(ddb, plan: dict, apply: bool) -> dict:
    """Write every entity row, then stamp the reel.

    Order matters and is not alphabetical: characters before projects, because a
    project's involvement links name character ids; projects before runs, scenes
    and movies, because each of those names its project. An interrupted `apply`
    therefore always leaves a prefix of the layer, never a row pointing at one
    that does not exist yet.

    An entity whose head row is already there is REPAIRED rather than skipped:
    every row it would have written is checked for attributes the stored one
    lacks, and only those are added. See `backfill` for why that is not a
    rewrite.
    """
    existing = plan["catalog"]["entities"]
    created, skipped = collections.Counter(), collections.Counter()
    repaired, added = collections.Counter(), collections.Counter()

    for kind in ("character", "project", "run", "scene", "movie"):
        for entity in plan[kind + "s"]:
            head = (f"{PARTITION[kind]}#{entity['id']}", "META")
            if head in existing:
                gaps = 0
                for group in GROUPS[kind](entity):
                    for action in group:
                        doc = action.get("Put", {}).get("Item")
                        if doc is None:
                            continue
                        names = backfill(ddb, ddbc.from_item(doc), apply)
                        gaps += len(names)
                        added.update(names)
                skipped[kind] += 1
                repaired[kind] += 1 if gaps else 0
                continue
            if not apply:
                created[kind] += 1
                continue
            wrote = False
            for group in GROUPS[kind](entity):
                if group:
                    wrote |= ddbc.transact(ddb, group)
            (created if wrote else skipped)[kind] += 1

    stamped = 0
    if apply:
        for node_id in plan["reel"]:
            stamped += 1 if stamp_reel(ddb, node_id, plan["lib"]) else 0
    else:
        stamped = len(plan["reel"])

    return {"created": dict(created), "skipped": dict(skipped),
            "repaired": dict(repaired), "added": dict(added), "reel": stamped}


# ── verify ──────────────────────────────────────────────────────────────────

def _list_bucket(s3) -> dict[str, int]:
    """Every object's size, by key. The independent side of the cross-check."""
    sizes = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3c.bucket()):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith("/"):
                sizes[obj["Key"]] = obj.get("Size", 0)
    return sizes


def phase_verify(s3, ddb, plan: dict) -> dict:
    """Re-read the table and re-list the bucket; check the two against each other.

    **Not as independent as the seed's `verify` was, and it says so rather than
    implying otherwise.** There the plan came from S3 and the rows from
    DynamoDB, so the two sides had genuinely separate origins. Here the entity
    layer is derived from the tree, which is also in DynamoDB — so the honest
    independent side is the BUCKET, and that is what every blob check below
    resolves against. What the table half proves is that the rows `apply`
    claimed to write are there, resolve to each other, and point at nodes that
    still exist.
    """
    sizes = _list_bucket(s3)
    lib = plan["lib"]

    rows: dict[tuple[str, str], dict] = {}
    nodes: dict[str, dict] = {}
    for item in ddbc.scan(ddb):
        pk, sk = item.get("pk", ""), item.get("sk", "")
        rows[(pk, sk)] = item
        if sk == "META" and pk.startswith("NODE#") and item.get("node_id"):
            nodes[item["node_id"]] = item

    problems: dict[str, list[str]] = collections.defaultdict(list)

    def node_exists(node_id: str | None) -> bool:
        return bool(node_id) and node_id in nodes

    def blob_exists(node_id: str) -> bool:
        key = nodes[node_id].get("blob_key")
        return bool(key) and key in sizes

    counted = collections.Counter()
    for kind in ("character", "project", "run", "scene", "movie"):
        partition = PARTITION[kind]
        for entity in plan[kind + "s"]:
            counted[kind] += 1
            record = rows.get((f"{partition}#{entity['id']}", "META"))
            if record is None:
                problems["missing_entity"].append(f"{kind} {entity['where']}")
                continue
            # The folder it adopted must exist and must point back. One field in
            # each direction; a break in either is a card the app cannot draw.
            root = entity.get("root") or entity.get("folder")
            if not node_exists(root):
                problems["missing_root"].append(f"{entity['where']}: {root}")
            elif nodes[root].get("entity") != entity["id"]:
                problems["no_back_pointer"].append(
                    f"{entity['where']}: {root} names "
                    f"{nodes[root].get('entity')!r}")

    for char in plan["characters"]:
        claim = rows.get((f"LIB#{lib}", f"CHARSLUG#{char['slug']}"))
        if claim is None or claim.get("entity") != char["id"]:
            problems["bad_slug_claim"].append(f"character {char['slug']}")
        for ref in char["refs"]:
            if rows.get((f"CHAR#{char['id']}", f"REF#{ref['node']}")) is None:
                problems["missing_reference"].append(
                    f"{char['where']}: {ref['node']}")
            elif not node_exists(ref["node"]):
                problems["dead_reference"].append(f"{char['where']}: {ref['node']}")
        for node_id in char["default_set"]:
            if not node_exists(node_id):
                problems["dead_default_set"].append(f"{char['where']}: {node_id}")

    for proj in plan["projects"]:
        claim = rows.get((f"LIB#{lib}", f"PROJSLUG#{proj['slug']}"))
        if claim is None or claim.get("entity") != proj["id"]:
            problems["bad_slug_claim"].append(f"project {proj['slug']}")

    for run in plan["runs"]:
        if rows.get((f"PROJ#{run['project']}",
                     f"RUN#{run['created']}#{run['id']}")) is None:
            problems["missing_listing_row"].append(run["where"])
        for node_id in run["outputs"]:
            if not node_exists(node_id):
                problems["dead_output"].append(f"{run['where']}: {node_id}")
            elif not blob_exists(node_id):
                problems["missing_output_blob"].append(f"{run['where']}: {node_id}")
        for name, node_id in (run["payload"] or {}).items():
            if node_id and not node_exists(node_id):
                problems["dead_payload"].append(f"{run['where']}: {name}")

    # **EVERY ROW MUST CARRY EVERY ATTRIBUTE IT WAS SUPPOSED TO CARRY.**
    #
    # The checks above ask whether a row EXISTS and whether the ids in it
    # resolve. All of them passed over the first prod migration, whose 32 entity
    # rows were each missing `id` — an attribute the API reads and the key alone
    # does not supply — so `VERIFY: PASS` was printed over a library whose
    # every listing returned 500. Existence was never the property worth
    # checking on its own.
    #
    # Rebuilt from `GROUPS` rather than from a list of required names, so this
    # cannot drift from what `apply` writes: the two read the same builders, and
    # an attribute added to a record is checked here the moment it is added
    # there. Same predicate as `backfill`, for the same reason.
    for kind in ("character", "project", "run", "scene", "movie"):
        for entity in plan[kind + "s"]:
            for group in GROUPS[kind](entity):
                for action in group:
                    doc = action.get("Put", {}).get("Item")
                    if doc is None:
                        continue
                    doc = ddbc.from_item(doc)
                    stored = rows.get((doc["pk"], doc["sk"]))
                    if stored is None:
                        continue  # already reported by the existence checks
                    thin = sorted(key for key, value in doc.items()
                                  if key not in stored and value is not None)
                    if thin:
                        problems["incomplete_row"].append(
                            f"{entity['where']}: {doc['pk']}/{doc['sk']} "
                            f"lacks {', '.join(thin)}")

    # D5, both directions. A qualifying file with no key is invisible in the
    # reel; a folder, a document or an entity row WITH one is the pollution the
    # sparse key exists to remove, and would be back the moment something wrote
    # it by hand.
    for row in nodes.values():
        if in_the_reel(row) and not row.get("reel"):
            problems["reel_unstamped"].append(row["node_id"])
        elif row.get("reel") and not in_the_reel(row):
            problems["reel_polluted"].append(f"{row['node_id']} ({row.get('kind')})")
    for (pk, sk), item in rows.items():
        if not pk.startswith(("NODE#", "LIB#", "USER#")) and item.get("reel"):
            problems["reel_polluted"].append(f"{pk}/{sk} (entity row)")

    drift = key_drift(plan, nodes)
    return {"ok": not problems, "problems": dict(problems),
            "entities": dict(counted), "objects": len(sizes),
            "drift": drift}


# ── reseat ──────────────────────────────────────────────────────────────────

def owners(plan: dict) -> dict[str, tuple[str, str]]:
    """`root node id -> (kind, entity id)` for the two kinds that own bytes.

    Runs, scenes and movies are deliberately absent. Their folders sit inside a
    project and their bytes are the project's — one prefix per project is what
    makes per-entity cost attribution and a bulk delete work, and a prefix per
    run would be thousands of them.
    """
    found = {}
    for kind in ("character", "project"):
        for entity in plan[kind + "s"]:
            found[entity["root"]] = (kind, entity["id"])
    return found


def desired_key(plan: dict, nodes: dict, node: dict) -> str:
    """Where a file node's bytes belong under `<owner_kind>/<owner_id>/<node_id>.<ext>`.

    The owner is DERIVED, from the node's `path` — the materialised list of
    ancestor ids the tree already maintains — by finding the nearest ancestor
    that some entity adopted. Nothing new is stored and nothing can drift; a
    move that changes the owner is visible here immediately, which is the whole
    reason `verify` can report drift at all.

    The extension is decoration for a human reading the console. `content_type`
    on the row is authoritative and the API sets it on every presigned response,
    so a node whose key has no suffix and whose type is unguessable simply gets
    none.
    """
    known = owners(plan)
    ancestors = [i for i in (node.get("path") or "").split("/") if i]
    kind, owner = None, None
    for ancestor in reversed(ancestors):
        if ancestor in known:
            kind, owner = known[ancestor]
            break
    prefix = OWNER_PREFIX[kind] if kind else LIBRARY_PREFIX
    owner = owner or plan["lib"]
    _, extension = os.path.splitext(node.get("blob_key") or "")
    if not extension:
        extension = mimetypes.guess_extension(node.get("content_type") or "") or ""
    return f"{prefix}/{owner}/{node['node_id']}{extension}"


def key_drift(plan: dict, nodes: dict) -> list[dict]:
    """Every file node whose key no longer describes its owner.

    Reported by `verify`, rewritten by `reseat`. **A drifted key is not broken.**
    It is a pointer, it resolves, and the bytes are exactly where the row says.
    What it has stopped being is legible — which is the trap the legacy keys set
    and the reason this is worth a command rather than a shrug.
    """
    drift = []
    for node in nodes.values():
        if node.get("kind") != "file" or not node.get("blob_key"):
            continue
        want = desired_key(plan, nodes, node)
        if node["blob_key"] != want:
            drift.append({"node": node["node_id"], "from": node["blob_key"],
                          "to": want})
    return sorted(drift, key=lambda d: d["from"])


def reseat_one(s3, ddb, entry: dict) -> str | None:
    """Copy, repoint, delete. In that order, and the order is the safety.

    Interrupted after the copy: two objects hold the same bytes, the row still
    names the old one, and a re-run repeats the copy — `CopyObject` onto the
    same key is idempotent. Interrupted after the row update: the old object is
    referenced by nothing, which is precisely what `catalog gc` collects. There
    is no ordering here that loses bytes, and every other ordering has one.
    """
    bucket = s3c.bucket()
    try:
        s3.copy_object(Bucket=bucket, Key=entry["to"],
                       CopySource={"Bucket": bucket, "Key": entry["from"]})
        ddb.update_item(
            TableName=ddbc.table(),
            Key=ddbc.to_item({"pk": f"NODE#{entry['node']}", "sk": "META"}),
            UpdateExpression="SET blob_key = :key",
            ExpressionAttributeValues=ddbc.to_item({":key": entry["to"]}),
            ConditionExpression="blob_key = :old",
            ExpressionAttributeValues2=None,
        )
    except Exception as error:  # noqa: BLE001 — boto3 raises generated classes
        return f"{entry['from']}: {type(error).__name__}: {error}"
    # No `VersionId`, ever. Naming a version is what turns a recoverable
    # tombstone into a permanent removal, and the grant that would allow it is
    # deliberately not held — see `catalog_gc.collect`, which says the same
    # thing about the same protection.
    try:
        s3.delete_object(Bucket=bucket, Key=entry["from"])
    except Exception as error:  # noqa: BLE001
        return f"{entry['from']}: copied and repointed, but not removed: {error}"
    return None


# ── the journal ─────────────────────────────────────────────────────────────

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


# ── the report ──────────────────────────────────────────────────────────────

def report(plan: dict) -> None:
    print(f"library    {plan['lib']}  ({plan['library_name']})")
    print(f"root node  {plan['root']}")
    print()
    print(f"{'entity':<12} {'n':>6}  adopts the folder it was read out of")
    print("-" * 78)
    for kind in ("character", "project", "run", "scene", "movie"):
        print(f"{kind + 's':<12} {len(plan[kind + 's']):>6}")
    refs = sum(len(c["refs"]) for c in plan["characters"])
    shots = sum(len(s["shots"]) for s in plan["scenes"])
    print("-" * 78)
    print(f"{'REF# rows':<12} {refs:>6}  one per reference image; order and group "
          "are attributes")
    print(f"{'SHOT# rows':<12} {shots:>6}  one per planned shot")
    print(f"{'reel':<12} {len(plan['reel']):>6}  image/video file nodes to stamp "
          "(D5: sparse by-recent)")
    print(f"{'polluted':<12} {plan['polluted']:>6}  rows carrying `reel` that "
          "should not — folders and documents")
    if plan["by_path"]:
        print(f"{'by path':<12} {len(plan['by_path']):>6}  resolved by NAME PATH, "
              "not by blob key — an assumption, see `resolve_key`")
        for entry in sorted(set(plan["by_path"]))[:SHOWN]:
            print(f"             {entry}")
        if len(set(plan["by_path"])) > SHOWN:
            print(f"             … and {len(set(plan['by_path'])) - SHOWN} more distinct")
    print(f"{'UNRESOLVED':<12} {len(plan['unresolved']):>6}  reported, does NOT "
          "block: a document names something the tree lost")
    for entry in plan["unresolved"][:SHOWN]:
        print(f"             {entry}")
    if len(plan["unresolved"]) > SHOWN:
        print(f"             … and {len(plan['unresolved']) - SHOWN} more")
    print(f"{'UNPARSEABLE':<12} {len(plan['unparseable']):>6}  "
          + ("" if not plan["unparseable"] else "<-- MUST BE 0 BEFORE `apply`"))
    for entry in plan["unparseable"]:
        print(f"             {entry}")

    example = next(iter(plan["characters"]), None) or next(iter(plan["projects"]), None)
    if example:
        print("\ne.g.")
        for field in ("kind", "id", "slug", "root", "where", "created"):
            print(f"  {field:<8} {example[field]}")


# ── CLI ─────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _session(journal_name, phase, apply=None, library=None):
    """The setup and teardown every phase shares.

    **Every phase takes a DynamoDB client, including `plan`.** The catalog
    seed's `plan` deliberately did not: it ran before the table existed and
    asking for one would have made the first useful command fail on
    infrastructure it did not need. That reasoning does not carry over — this
    command reads the entity layer OUT of the table, so a plan without one has
    nothing to plan from.
    """
    s3 = s3c.client()
    ddb = ddbc.client()
    if not ddbc.table_exists(ddb):
        die(f"no table '{ddbc.table()}' — it is created by studio's Terraform. "
            "Apply the infra first, or set STUDIO_CATALOG_TABLE.")
    jpath = journal_path(journal_name)
    journal = load_journal(jpath)
    plan = build_plan(s3, ddb, library)
    if phase != "plan":
        if plan["unparseable"]:
            die(f"{len(plan['unparseable'])} unparseable document(s) — run "
                "`studio catalog migrate plan` and resolve them first")
        total = sum(len(plan[k + "s"])
                    for k in ("character", "project", "run", "scene", "movie"))
        print(f"[{'APPLY' if apply else 'dry run'}] {phase}: "
              f"{total} entit(y|ies) in scope\n")
    try:
        yield s3, ddb, plan, journal
    finally:
        save_journal(jpath, journal)
        print(f"journal: {jpath}")


@click.group(help=__doc__)
def main():
    pass


@main.group("migrate", help=__doc__,
            short_help="raise entity rows over an already-recorded library")
def cmd_migrate():
    pass


@cmd_migrate.command("plan")
@click.option("--library", help="Which library to migrate. Required only when the table holds more than one, which prod always does — `lib-smoke` is seeded by the post-deploy smoke test.")
@click.option("--journal", help="journal file name (default: the newest)")
def do_plan(library, journal):
    """Show the entity rows that would be created, and what cannot be read."""
    with _session(journal, "plan", library=library) as (_s3, _ddb, plan, jrn):
        report(plan)
        jrn["migrate_plan"] = {
            "lib": plan["lib"], "root": plan["root"],
            "counts": {k: len(plan[k + "s"]) for k in
                       ("character", "project", "run", "scene", "movie")},
            "reel": len(plan["reel"]), "polluted": plan["polluted"],
            "unparseable": plan["unparseable"],
            "unresolved": plan["unresolved"],
            "by_path": sorted(set(plan["by_path"])),
            # A sample, not the map. Every id here is a pure function of the
            # catalog, so the mapping is re-derivable and a copy of it in the
            # journal would only rot — the same call the catalog seed made.
            "sample": [{"kind": e["kind"], "id": e["id"], "slug": e["slug"],
                        "root": e["root"], "where": e["where"]}
                       for e in (plan["characters"] + plan["projects"])[:20]],
        }
    if plan["unparseable"]:
        raise SystemExit(1)


@cmd_migrate.command("apply")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--library", help="Which library to migrate. Required only when the table holds more than one, which prod always does — `lib-smoke` is seeded by the post-deploy smoke test.")
@click.option("--journal", help="journal file name (default: the newest)")
def do_apply(apply, library, journal):
    """Create the entity rows. Adopts folders; copies no bytes; deletes nothing."""
    with _session(journal, "apply", apply, library=library) as (_s3, ddb, plan, jrn):
        res = phase_apply(ddb, plan, apply)
        verb = "created" if apply else "would create"
        for kind in ("character", "project", "run", "scene", "movie"):
            print(f"{kind + 's':<12} {res['created'].get(kind, 0):>6} {verb}"
                  f"   {res['skipped'].get(kind, 0):>6} already there"
                  f"   {res['repaired'].get(kind, 0):>6} repaired")
        print(f"{'reel':<12} {res['reel']:>6} {verb.replace('create', 'stamp')}"
              "   (image/video file nodes only)")
        # Named rather than counted: an attribute an older version of this file
        # forgot is the thing worth reading off the console, and there are only
        # ever a handful of distinct names.
        for name, count in sorted(res["added"].items()):
            print(f"{'':<12} {count:>6} row(s) "
                  f"{'given' if apply else 'would be given'} {name}")
        if apply:
            jrn["migrate_apply"] = {"lib": plan["lib"], "created": res["created"],
                                    "skipped": res["skipped"],
                                    "repaired": res["repaired"],
                                    "added": res["added"], "reel": res["reel"]}


@cmd_migrate.command("verify")
@click.option("--library", help="Which library to migrate. Required only when the table holds more than one, which prod always does — `lib-smoke` is seeded by the post-deploy smoke test.")
@click.option("--journal", help="journal file name (default: the newest)")
def do_verify(library, journal):
    """Check every entity resolves, every folder exists, every output is there."""
    with _session(journal, "verify", library=library) as (s3, ddb, plan, jrn):
        res = phase_verify(s3, ddb, plan)
        for kind, count in sorted(res["entities"].items()):
            print(f"{kind + 's':<22} {count}")
        print(f"{'objects in the bucket':<22} {res['objects']}")
        print(f"{'keys that have drifted':<22} {len(res['drift'])}   "
              "(not broken — `reseat` rewrites them)")
        for label, entries in sorted(res["problems"].items()):
            print(f"\n{label.upper()}  {len(entries)}")
            for entry in entries[:SHOWN]:
                print(f"  {entry}")
            if len(entries) > SHOWN:
                print(f"  … and {len(entries) - SHOWN} more")
        print("\nVERIFY: " + ("PASS" if res["ok"] else "FAIL"))
        jrn["migrate_verify"] = {
            "ok": res["ok"], "entities": res["entities"],
            "objects": res["objects"], "drift": len(res["drift"]),
            "problems": {k: v[:50] for k, v in res["problems"].items()},
        }
    if not res["ok"]:
        raise SystemExit(1)


@main.command("reseat", help=__doc__,
              short_help="rewrite blob keys whose owner prefix has drifted")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--library", help="Which library to migrate. Required only when the table holds more than one, which prod always does — `lib-smoke` is seeded by the post-deploy smoke test.")
@click.option("--journal", help="journal file name (default: the newest)")
def cmd_reseat(apply, library, journal):
    """Move drifted blobs to `<owner_kind>/<owner_id>/<node_id>.<ext>`.

    Optional, separate and never automatic. It refuses until the journal records
    a passing `verify`, because it is the only command in this file that deletes
    an object and the check that says the rows are right has to have run first.
    """
    with _session(journal, "reseat", apply, library=library) as (s3, ddb, plan, jrn):
        if not (jrn.get("migrate_verify") or {}).get("ok"):
            die("this journal records no passing `verify`. Run "
                "`studio catalog migrate verify` first — reseat deletes objects "
                "and will not do that against rows nobody has checked.")
        nodes = plan["catalog"]["nodes"]
        drift = key_drift(plan, nodes)
        print(f"{'drifted':<12} {len(drift):>6}  file nodes whose key no longer "
              "names their owner")
        for entry in drift[:SHOWN]:
            print(f"  {entry['from']}\n    -> {entry['to']}")
        if len(drift) > SHOWN:
            print(f"  … and {len(drift) - SHOWN} more")

        if not apply:
            print("\nnothing moved. `--apply` rewrites exactly what is listed above.")
            jrn["reseat"] = {"drift": [d["from"] for d in drift]}
            return

        failed = [problem for entry in drift
                  if (problem := reseat_one(s3, ddb, entry)) is not None]
        print(f"\n{'reseated':<12} {len(drift) - len(failed):>6}")
        for problem in failed:
            print(f"FAILED       {problem}")
        jrn["reseat_applied"] = {"reseated": len(drift) - len(failed),
                                 "failed": failed}
    if apply and failed:
        raise SystemExit(1)
