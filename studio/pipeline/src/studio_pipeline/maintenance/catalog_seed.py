"""`studio catalog` — record the bucket that already exists in the catalog.

The catalog (`studio-<env>-catalog`, one DynamoDB table) becomes the library:
identity, name, parent and owner are rows, and an S3 key is an opaque pointer
nothing derives or parses. This command is the first write to it — it inventories
the bucket as it stands and gives every folder and object a row.

    Library   lib-<uuid>     the sharing unit; has members
     └ Node   node-<uuid>    a folder or a file, with a parent pointer

**IT COPIES NOTHING, MOVES NOTHING AND DELETES NOTHING.** Every existing
`characters/<slug>/…` and `projects/<slug>/…` key stays exactly where it is and
is simply recorded as a node's `blob_key`. That is also why there is no rewrite
phase here: a rewrite exists to patch the keys recorded *inside* documents when
objects move, and nothing moves.

THREE PHASES, EACH ITS OWN INVOCATION
-------------------------------------
    plan     walk the bucket; report the node tree that would be created.
             Touches S3 only — it runs before the table exists.
    seed     create the library, its root node, and one node per folder and
             object. `blob_key` is the key that already exists.
    verify   read the table back and re-list the bucket: every node's blob
             resolves, and every object is claimed by exactly one node.

Every phase is `--dry-run` unless `--apply`, and they are separate commands
because the ordering between them is the safety property — the same reason the
`migrate-layout` command this shape was inherited from split its five. The
journal (`local/migrations/<ts>.json`, git-ignored) records what each phase did.
Nothing about the seed is ever written into the bucket.

EVERYTHING HERE IS A PURE FUNCTION OF THE BUCKET
------------------------------------------------
Ids are derived (uuid5 over `s3://<bucket>/<key>`), not drawn at random, and
timestamps are derived from `LastModified`. No phase reads a clock.

That is load-bearing, not tidiness. The three phases each rebuild the plan from
a fresh listing, so `seed` and `verify` can only agree with `plan` if the plan
is reproducible. Random ids would make a resumed seed create a *second* tree
beside the half-written first one, because nothing would recognise the nodes
already there. It is the same property the layout migrator got from keeping its
key map in `paths.py`: the code that writes the map and the code that checks it
agree by construction.

A derived id is still an opaque id. Nothing reads one back to recover a key, and
a later rename or move breaks any correspondence anyway — the derivation exists
only for the one moment the tree is being created.

TIES, AND WHY `created_at` IS NOT JUST `LastModified`
-----------------------------------------------------
S3's `LastModified` has one-second resolution and a run writes its whole output
inside one second, so equal timestamps are the common case rather than the edge.
That is why `services/browse.py::_sort_records` used to break ties on the full
key in a second pass. The catalog's `created_at` retired that workaround, and
this is where it is paid for: the tie is resolved once, here, at the only moment
the key is still available to resolve it with — objects sharing a second are
ordered by key and given consecutive microseconds. `_sort_records` now sorts on
one field, and it reproduces the ordering the two passes gave.

WHAT IS NOT A NODE
------------------
`config/` and `phrasebook/` are shared — they belong to no character, no project
and no library (`paths.py` says why they sit outside both trees). They are read
directly and never recorded, so `verify` counts an object under them as
legitimately unclaimed rather than as an orphan.

Nor is this command for a bucket the API has already written to. `blobs/<node_id>`
keys arrive with their row already in place; a bucket holding them is past the
point where an inventory of "what exists but has no row" means anything.
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

from studio_pipeline.errors import die
from studio_pipeline import STUDIO_DIR  # noqa: E402
from studio_pipeline.adapters import ddb as ddbc  # noqa: E402
from studio_pipeline.adapters import s3 as s3c  # noqa: E402
from studio_pipeline.domain import paths as P  # noqa: E402

JOURNAL_DIR = str(STUDIO_DIR / "local" / "migrations")

# Owned by nobody. See the docstring.
SHARED_PREFIXES = (P.CONFIG + "/", P.PHRASEBOOK + "/")

# uuid5 over a URL is what NAMESPACE_URL is for, and an `s3://` URL is the one
# globally unique name an object already has — so two buckets never derive the
# same node id, and re-running against the same bucket always does.
_NAMESPACE = uuid.NAMESPACE_URL




# ── identity ────────────────────────────────────────────────────────────────

def library_id() -> str:
    """One bucket, one library. The bucket names it."""
    return "lib-" + str(uuid.uuid5(_NAMESPACE, f"s3://{s3c.bucket()}"))


def node_id(path: str) -> str:
    """The id for the node at `path`; `""` is the library root."""
    return "node-" + str(uuid.uuid5(_NAMESPACE, f"s3://{s3c.bucket()}/{path}"))


def materialised(prefix: str) -> str:
    """The `path` attribute for a node sitting directly inside `prefix`.

    Ancestor ids, root first, slash-delimited: `/node-a/node-b/`. The root's own
    path is `/` because it has no ancestors, so a node at the library root gets
    `/<root_id>/`. `parent_id` stays authoritative; this is the derived index
    that makes a subtree a `begins_with` query.
    """
    ids = [node_id("")]
    if prefix:
        parts = prefix.split("/")
        ids += [node_id("/".join(parts[:i + 1])) for i in range(len(parts))]
    return "/" + "/".join(ids) + "/"


def clean_name(name: str) -> str | None:
    """Why a path segment cannot be a node name, or None if it can.

    Mirrors the API's `services/keys.py::clean_name`, which is the validator the
    schema names — deliberately a copy rather than an import, because the two
    halves of studio are separate packages and the pipeline depends on neither
    the backend nor its Flask stack. It returns a reason instead of raising so
    `plan` can report every bad name at once rather than stopping at the first.
    """
    if not name:
        return "empty path segment"
    if name in (".", ".."):
        return "name may not be '.' or '..'"
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        return "name contains control characters"
    if len(name.encode("utf-8")) > 255:
        return "name is longer than 255 bytes"
    return None


# ── the plan ────────────────────────────────────────────────────────────────

def _list_bucket(s3) -> dict:
    """Every object, split into what this command does with it.

    Shared by `plan` and `verify`; `verify` re-lists rather than trusting the
    plan it just wrote, which is the only thing that makes the check
    non-circular.
    """
    files, markers, shared = [], [], []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3c.bucket()):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.startswith(SHARED_PREFIXES):
                shared.append(key)
            elif key.endswith("/"):
                # An empty-folder marker carries no bytes. It still names a
                # folder, so its prefix becomes a node — but the marker object
                # itself is never a file node, exactly as the migrator never
                # moved one.
                markers.append((key, obj["LastModified"]))
            else:
                files.append((key, obj["LastModified"], obj.get("Size", 0)))
    return {"files": files, "markers": markers, "shared": shared,
            "sizes": {key: size for key, _lm, size in files}}


def created_stamps(files) -> dict[str, str]:
    """One distinct, correctly ordered `created_at` per object key.

    Objects sharing a `LastModified` second are ordered by key and given
    consecutive microseconds — see the module docstring. A second holds a
    million of them and no S3 second has ever held anything near that many
    objects, so an offset cannot run into the next second's stamps.
    """
    by_second = collections.defaultdict(list)
    for key, last_modified, _size in files:
        by_second[last_modified].append(key)
    stamps = {}
    for second, keys in by_second.items():
        for offset, key in enumerate(sorted(keys)):
            stamps[key] = _iso(second + dt.timedelta(microseconds=offset))
    return stamps


def _iso(moment: dt.datetime) -> str:
    """ISO-8601 with the microseconds always spelled out.

    `isoformat()` omits the fractional part when it is zero, which makes the
    stamps different lengths and their lexical order stop matching their
    chronological one — and lexical is how they are compared, both in a
    `by-recent` query and in this module.
    """
    return moment.isoformat(timespec="microseconds")


def build_plan(s3) -> dict:
    """The whole node tree, parents before children. Reports what cannot be one."""
    listing = _list_bucket(s3)
    stamps = created_stamps(listing["files"])
    lib = library_id()
    unmapped: list[str] = []

    # A folder's `created_at` is the earliest of everything beneath it: the
    # folder did not exist before its first object did, and seeding it from the
    # clock would sort every folder in the library above every file under
    # `by-recent`.
    folders: dict[str, str] = {}

    def note_folder(prefix: str, when: str) -> None:
        if prefix and (prefix not in folders or when < folders[prefix]):
            folders[prefix] = when

    for key, when in stamps.items():
        parts = key.split("/")
        for depth in range(1, len(parts)):
            note_folder("/".join(parts[:depth]), when)
    for key, last_modified in listing["markers"]:
        when = _iso(last_modified)
        parts = key.rstrip("/").split("/")
        for depth in range(1, len(parts) + 1):
            note_folder("/".join(parts[:depth]), when)

    if not stamps:
        die("no objects to record — the bucket holds nothing outside "
            f"{' and '.join(SHARED_PREFIXES)}")

    # The root is a real row, and the only node with neither a `parent_id` nor a
    # `name`. Both absences say the same thing — it is not a child of anything —
    # and the missing `parent_id` is what lets rename, move and delete of the
    # root refuse on the data rather than on a special case. It follows that the
    # root is ONE item, not two: the `NAME#` item exists to pair a name with a
    # parent, and there is neither. Its display name is the library's `name`.
    #
    # Its `created_at` is the oldest thing in the bucket, for the same reason no
    # other value here comes from a clock — the phases have to agree.
    born = min(stamps.values())
    nodes: list[dict] = [{
        "node_id": node_id(""), "parent_id": None, "lib": lib, "name": None,
        "kind": "folder", "path": "/", "created_at": born, "updated_at": born,
    }]

    taken: dict[tuple[str, str], str] = {}

    def claim(parent_prefix: str, name: str, what: str) -> bool:
        """A name is unique within its folder — that is what the index item is."""
        slot = (parent_prefix, name)
        if slot in taken:
            unmapped.append(f"{what}  (name '{name}' already taken in "
                            f"'{parent_prefix or '/'}' by {taken[slot]})")
            return False
        taken[slot] = what
        return True

    def child(prefix: str, when: str, **extra) -> dict | None:
        parent_prefix, _, name = prefix.rpartition("/")
        if (why := clean_name(name)) is not None:
            unmapped.append(f"{prefix}  ({why})")
            return None
        if not claim(parent_prefix, name, prefix):
            return None
        return {"node_id": node_id(prefix), "parent_id": node_id(parent_prefix),
                "lib": lib, "name": name, "path": materialised(parent_prefix),
                "created_at": when, "updated_at": when, **extra}

    # Folders first, and `sorted` is enough to put a parent before its child: a
    # parent's key is a proper prefix of its child's, so it always sorts first.
    # Nothing here can be written before its parent exists.
    for prefix in sorted(folders):
        if (node := child(prefix, folders[prefix], kind="folder")) is not None:
            nodes.append(node)
    for key, _last_modified, size in sorted(listing["files"]):
        node = child(key, stamps[key], kind="file", blob_key=key, size=size,
                     content_type=content_type(key))
        if node is not None:
            nodes.append(node)

    return {"lib": lib, "root": node_id(""), "nodes": nodes,
            "markers": [k for k, _ in listing["markers"]],
            "shared": listing["shared"], "unmapped": unmapped}


def content_type(key: str) -> str:
    """Guessed from the extension, not read back with a HEAD.

    Every writer in this package sets `ContentType` from exactly this call
    (`objects/upload.py`, `domain/runs.py`, `domain/characters/`), so guessing
    reproduces what is stored for anything the pipeline wrote — at zero
    requests, against a bucket with thousands of objects. `content_type` is a
    node attribute the API may correct later; a HEAD per object to seed it would
    be the most expensive part of this command by an order of magnitude.
    """
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


def report(plan: dict) -> None:
    kinds = collections.Counter(n["kind"] for n in plan["nodes"])
    depth = collections.Counter(n["path"].count("/") - 1 for n in plan["nodes"])

    print(f"library    {plan['lib']}")
    print(f"root node  {plan['root']}    (path '/', no parent)")
    print()
    print(f"{'depth':<12} {'n':>6}  nodes at each level (0 is the root itself)")
    print("-" * 78)
    for level in sorted(depth):
        print(f"{level:<12} {depth[level]:>6}")
    print("-" * 78)
    print(f"{'folders':<12} {kinds['folder']:>6}  folder nodes (one per key prefix)")
    print(f"{'files':<12} {kinds['file']:>6}  file nodes (blob_key = the key that exists)")
    print(f"{'TOTAL':<12} {len(plan['nodes']):>6}  nodes, 2 items each "
          "(the root is 1: no parent, so no NAME# item)")
    print(f"{'markers':<12} {len(plan['markers']):>6}  empty folder markers "
          f"(their prefix is a node; the object is not)")
    print(f"{'shared':<12} {len(plan['shared']):>6}  "
          f"{' + '.join(SHARED_PREFIXES)} — owned by no library")
    print(f"{'UNMAPPED':<12} {len(plan['unmapped']):>6}  "
          + ("" if not plan["unmapped"] else "<-- BLOCKS EVERYTHING BELOW"))
    for entry in plan["unmapped"]:
        print(f"             {entry}")

    example = next((n for n in plan["nodes"] if n["kind"] == "file"), None)
    if example:
        print("\ne.g.")
        for field in ("node_id", "parent_id", "name", "kind", "blob_key",
                      "size", "content_type", "path", "created_at"):
            print(f"  {field:<13} {example[field]}")


# ── seed ────────────────────────────────────────────────────────────────────

def meta_item(node: dict) -> dict:
    """`NODE#<node_id>` / `META` — every attribute the node has."""
    item = {"pk": f"NODE#{node['node_id']}", "sk": "META"}
    item.update({k: v for k, v in node.items() if v is not None})
    # Nothing has been updated yet, and a null `updated_at` would make every
    # consumer branch on "never touched". It equals `created_at` until a write.
    item["updated_at"] = node["updated_at"]
    return item


def index_item(node: dict) -> dict:
    """`NODE#<parent_id>` / `NAME#<name>` — the by-parent listing item.

    Deliberately narrow: `node_id, lib, kind, path, created_at` and nothing
    else. `size` and `content_type` are mutable, so duplicating them here would
    put every rename, move and text edit in the business of keeping two copies
    in step. A listing that wants file metadata queries children and then
    `BatchGetItem`s the `META` rows — 1 + ceil(n/100) round trips, not an N+1.
    """
    return {"pk": f"NODE#{node['parent_id']}", "sk": f"NAME#{node['name']}",
            "node_id": node["node_id"], "lib": node["lib"], "kind": node["kind"],
            "path": node["path"], "created_at": node["created_at"]}


def already_seeded(ddb, lib: str) -> tuple[bool, set[str]]:
    """Whether the library row exists, and which node ids it already has.

    One scan. A `get_item` per node would be thousands of round trips to answer
    a question one pass over the table answers, and the condition expressions on
    the writes are still the real guard — this is what lets the *dry run* say how
    much is left to do, which is the whole point of running one.
    """
    library, nodes = False, set()
    for item in ddbc.scan(ddb):
        if item.get("pk") == f"LIB#{lib}" and item.get("sk") == "META":
            library = True
        elif (item.get("lib") == lib and item.get("sk") == "META"
                and item.get("node_id")):
            nodes.add(item["node_id"])
    return library, nodes


def phase_seed(ddb, plan: dict, owner_sub: str, library_name: str,
               apply: bool) -> dict:
    library_exists, existing = already_seeded(ddb, plan["lib"])
    root = plan["nodes"][0]

    # The library, its owner's membership and its root node go together in one
    # transaction. A library whose root row is missing is not a half-created
    # library, it is a broken one: every `create_node` at the library root reads
    # the parent's `path` and fails.
    library = [
        ddbc.put({"pk": f"LIB#{plan['lib']}", "sk": "META", "name": library_name,
                  "root_node": plan["root"], "created_at": root["created_at"]}),
        ddbc.put({"pk": f"USER#{owner_sub}", "sk": f"LIB#{plan['lib']}",
                  "role": "owner", "created_at": root["created_at"]}),
        ddbc.put(meta_item(root)),
    ]
    library_created = not library_exists
    if apply:
        library_created = ddbc.transact(ddb, library)

    created, skipped = [], []
    for node in plan["nodes"][1:]:
        if node["node_id"] in existing:
            skipped.append(node["node_id"])
            continue
        if not apply:
            created.append(node["node_id"])
            continue
        # Two items, one transaction. That is the price of getting
        # list-by-parent and unique-name-per-folder out of one table, and it is
        # paid per node rather than per batch so an interrupted seed leaves no
        # half-written node behind.
        wrote = ddbc.transact(ddb, [ddbc.put(meta_item(node)),
                                    ddbc.put(index_item(node))])
        (created if wrote else skipped).append(node["node_id"])

    return {"library_created": library_created, "created": created,
            "skipped": skipped}


# ── verify ──────────────────────────────────────────────────────────────────

def phase_verify(s3, ddb, plan: dict) -> dict:
    """Read the table back and re-list the bucket; cross-check the two.

    Deliberately not a comparison of the plan against itself. The rows come from
    DynamoDB and the objects from a fresh `ListObjectsV2`, so this fails if the
    seed wrote nothing, wrote it wrong, or the bucket moved underneath it.
    """
    listing = _list_bucket(s3)
    lib = plan["lib"]

    library = None
    members, metas, index = [], {}, collections.defaultdict(list)
    for item in ddbc.scan(ddb):
        pk, sk = item.get("pk", ""), item.get("sk", "")
        if pk == f"LIB#{lib}" and sk == "META":
            library = item
        elif sk == f"LIB#{lib}":
            members.append(pk)
        elif item.get("lib") != lib:
            continue
        elif sk == "META":
            metas[item["node_id"]] = item
        elif sk.startswith("NAME#"):
            index[item["node_id"]].append((pk, sk))

    problems: dict[str, list[str]] = collections.defaultdict(list)
    if library is None:
        problems["no_library"].append(f"LIB#{lib}")
    elif library.get("root_node") not in metas:
        problems["no_root"].append(str(library.get("root_node")))
    if not members:
        problems["no_member"].append(f"nothing holds LIB#{lib}")

    root_id = (library or {}).get("root_node")
    claims: dict[str, list[str]] = collections.defaultdict(list)
    for node_key, node in metas.items():
        # The root is one item; every other node is two, and a node missing its
        # index item is invisible to a folder listing while looking fine by id.
        if node_key == root_id:
            if node.get("parent_id") or node.get("path") != "/":
                problems["bad_root"].append(f"{node_key}: root has a parent or a path")
            continue
        if not index.get(node_key):
            problems["no_index_item"].append(node_key)
        elif len(index[node_key]) > 1:
            problems["duplicate_index_item"].append(node_key)
        parent = metas.get(node.get("parent_id"))
        if parent is None:
            problems["orphan"].append(f"{node_key}: parent {node.get('parent_id')} is gone")
        elif node.get("path") != parent["path"] + parent["node_id"] + "/":
            problems["path_drift"].append(f"{node_key}: {node.get('path')}")
        if node.get("kind") != "file":
            continue
        blob = node.get("blob_key")
        if blob not in listing["sizes"]:
            problems["missing_blob"].append(f"{node_key}: {blob}")
            continue
        claims[blob].append(node_key)
        if node.get("size") != listing["sizes"][blob]:
            problems["size_drift"].append(
                f"{blob}: row says {node.get('size')}, object is "
                f"{listing['sizes'][blob]}")

    for blob, owners in claims.items():
        if len(owners) > 1:
            problems["claimed_twice"].append(f"{blob}: {', '.join(owners)}")
    for key in listing["sizes"]:
        if key not in claims:
            problems["unclaimed"].append(key)

    # Not a problem, and reported so it is visible that they were considered:
    # a shared object belongs to no library, so nothing claiming it is correct.
    ok = not problems
    return {"ok": ok, "problems": dict(problems), "nodes": len(metas),
            "members": len(members), "objects": len(listing["sizes"]),
            "claimed": len(claims), "shared": len(listing["shared"]),
            "markers": len(listing["markers"])}


# ── the journal ─────────────────────────────────────────────────────────────

def journal_path(name: str | None) -> str:
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    if name:
        return os.path.join(JOURNAL_DIR, name if name.endswith(".json") else name + ".json")
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


# ── CLI ─────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _session(journal_name, phase, apply=None, needs_table=False):
    """The setup and teardown every phase shares.

    `plan` deliberately takes no DynamoDB client: it is the phase that runs
    *before* the table exists, and asking for one would make the first useful
    command fail on infrastructure it does not need.
    """
    s3 = s3c.client()
    ddb = ddbc.client() if needs_table else None
    jpath = journal_path(journal_name)
    journal = load_journal(jpath)
    plan = build_plan(s3)
    if phase != "plan":
        if plan["unmapped"]:
            die(f"{len(plan['unmapped'])} unmapped key(s) — run `plan` and resolve them first")
        if not ddbc.table_exists(ddb):
            die(f"no table '{ddbc.table()}' — it is created by studio's Terraform. "
                "Apply the infra first, or set STUDIO_CATALOG_TABLE.")
        print(f"[{'APPLY' if apply else 'dry run'}] {phase}: "
              f"{len(plan['nodes'])} node(s) in scope\n")
    try:
        yield s3, ddb, plan, journal
    finally:
        save_journal(jpath, journal)
        print(f"journal: {jpath}")


@click.group(help=__doc__)
def main():
    pass


@main.command("plan")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_plan(apply, journal):
    """Show the node tree that would be created, and record its shape."""
    with _session(journal, "plan", apply) as (_s3, _ddb, plan, jrn):
        report(plan)
        kinds = collections.Counter(n["kind"] for n in plan["nodes"])
        jrn["plan"] = {
            "lib": plan["lib"], "root": plan["root"],
            "folders": kinds["folder"], "files": kinds["file"],
            "markers": len(plan["markers"]), "shared": len(plan["shared"]),
            "unmapped": plan["unmapped"],
            # A sample, not the map. The migrator journals its whole mapping
            # because nothing else can reconstruct it; here every id and stamp
            # is a pure function of the bucket, so the map is re-derivable and
            # a 5,000-entry copy of it in the journal would only rot.
            "sample": plan["nodes"][:20],
        }
    if plan["unmapped"]:
        raise SystemExit(1)


@main.command("seed")
@click.option("--owner-sub", required=True,
              help="Cognito `sub` of the library's owner (the membership row)")
@click.option("--library-name", default="Studio", show_default=True,
              help="display name for the library")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_seed(owner_sub, library_name, apply, journal):
    """Create the library, its root node, and one node per folder and object."""
    with _session(journal, "seed", apply, needs_table=True) as (_s3, ddb, plan, jrn):
        res = phase_seed(ddb, plan, owner_sub, library_name, apply)
        print(f"library   {plan['lib']}  "
              + ("created" if res["library_created"] else "already there"))
        print(f"owner     USER#{owner_sub} -> owner")
        print(f"{'created' if apply else 'would create'}   {len(res['created'])} node(s)")
        print(f"skipped   {len(res['skipped'])}  (already seeded)")
        if apply:
            jrn["seed"] = {"lib": plan["lib"], "root": plan["root"],
                           "library_name": library_name,
                           "library_created": res["library_created"],
                           "created": len(res["created"]),
                           "skipped": len(res["skipped"])}


@main.command("verify")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_verify(apply, journal):
    """Check every node's blob resolves and every object is claimed once."""
    with _session(journal, "verify", apply, needs_table=True) as (s3, ddb, plan, jrn):
        res = phase_verify(s3, ddb, plan)
        print(f"nodes in the table     {res['nodes']}")
        print(f"members                {res['members']}")
        print(f"objects in the bucket  {res['objects']}")
        print(f"claimed exactly once   {res['claimed']}")
        print(f"shared, so unclaimed   {res['shared']}   "
              f"({' + '.join(SHARED_PREFIXES)} — belong to no library)")
        print(f"folder markers         {res['markers']}   (not objects a node claims)")
        for label, entries in sorted(res["problems"].items()):
            print(f"\n{label.upper()}  {len(entries)}")
            for entry in entries[:10]:
                print(f"  {entry}")
            if len(entries) > 10:
                print(f"  … and {len(entries) - 10} more")
        print("\nVERIFY: " + ("PASS" if res["ok"] else "FAIL"))
        jrn["verify"] = {"ok": res["ok"], "nodes": res["nodes"],
                         "objects": res["objects"], "claimed": res["claimed"],
                         "problems": {k: v[:50] for k, v in res["problems"].items()}}
    if not res["ok"]:
        raise SystemExit(1)
