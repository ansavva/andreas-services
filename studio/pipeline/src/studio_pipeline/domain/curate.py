"""`studio curate` — maintain a character's image pools: dedupe, move, groups.

Curating by hand goes wrong the same ways every time: duplicates creep in under
different names, and "replacing" an image quietly destroys the only copy. This
does those operations safely.

Four pools, per `studio-media-character`:

    reference/   images the character's `REF#` rows point at — who they ARE.
    corpus/      collected material — uploads, keeper clips.
    seed/        the founding real-world source photos.
    archive/     retired material; never referenced unless asked for by name.

Nothing is deleted outright: an image leaving a pool is moved, and destroyed
only when a byte-identical copy is already waiting where it was going. Every
command is a DRY RUN unless you pass --apply.

  studio curate dedupe <name> --pool reference --group face
  studio curate move <name> face/front-neutral.webp --from reference --to archive
  studio curate groups <name>

MOVING AN IMAGE NO LONGER MOVES ANYTHING ELSE
---------------------------------------------
**This section used to be headed "MOVING AN IMAGE STILL MOVES ITS RECORDS", and
it was the largest unfinished thing in the pipeline.** It said, correctly at the
time, that a record did not name a node — it named a **path** — so renaming
`face/<slug>_3.png` left every run that cited it pointing at a path that no
longer resolved. `domain/rewrite.py` existed to sweep those documents, every
command here called `rewrite.apply_moves`, and skipping that step is what once
left 69 records pointing at reference images that no longer existed.

Records name **node ids** now. A node id survives a rename, a reparent, a
regroup and a move of the character it belongs to, because none of those touch
it. So there is nothing to sweep: `rewrite.py` is deleted, `rewrite check` is
deleted, and every call to `apply_moves` in this module is deleted. It is the
single largest simplification in the entity model, and this module is where it
shows most — three commands that each ended in a document-rewriting pass now
end after the operation itself.

WHAT ELSE IS NO LONGER HERE
---------------------------
`renumber` closed holes in a reference group's numbering, because ORDER WAS THE
TRAILING NUMBER IN A FILENAME. Order is `order` on the `REF#` row, gapped by
1000, so there are no holes to close and nothing to renumber — the command has
no work left to do at all. Explicit ordering is `studio character order`.

`regroup` moved reference images into a purpose subfolder and rewrote every
record citing them. A group is an attribute of a row, so it moved to
`studio character regroup`, where it is one `PATCH` and writes no object.

`set-refs` rebuilt `reference/` from chosen numbers, because the folder WAS the
set that got sent. The `default_set` names what is sent; choosing is
`studio character default-set`.

`dedupe` still reads bytes, because comparing them is the point. It reads fewer
than it did: the catalog records each file's size, so only same-size files can
be identical and only those are hashed.
"""
from __future__ import annotations

import hashlib
import os
import sys

import click

from studio_pipeline.adapters import api, entities, store
from studio_pipeline.domain.characters import (
    IMG_EXTS,
    pool_folder,
    pool_nodes,
    resolve,
)
from studio_pipeline.errors import die

POOL_CHOICES = ["archive", "corpus", "reference", "seed"]
# The caps are prose-only in every model's schema (maxItems is null), so they are
# maintained here by hand. The lowest one binds a set that is sent in full.
ENGINE_CAPS = {"kling": 7, "seedance": 9, "nano-banana": 14}


def images(record: dict, pool: str, group: str | None = None) -> list[dict]:
    """The image nodes in a pool, or in one of its subfolders."""
    return [entry for entry in pool_nodes(record, pool, group)
            if os.path.splitext(entry["name"])[1].lower() in IMG_EXTS]


def digest(node_id: str) -> str:
    """Content hash of one image. Only ever called on same-size candidates."""
    return hashlib.md5(store.read_node(node_id)).hexdigest()


def duplicate_pairs(entries: list[dict]) -> list[tuple[dict, dict]]:
    """(duplicate, keeper) for every byte-identical pair, cheapest test first.

    **Size is checked before bytes are read**, which the S3 version did not do —
    it hashed every object in the pool. Two files of different sizes cannot be
    identical, so this is exact rather than a heuristic, and it matters more now
    than it did: a read is an HTTPS round trip out of the bucket rather than a
    `GetObject` inside it, so hashing a forty-image pool to find no duplicates
    was about to become forty downloads.
    """
    by_size: dict[int, list[dict]] = {}
    for entry in entries:
        by_size.setdefault(int(entry.get("size") or 0), []).append(entry)

    dupes = []
    for candidates in by_size.values():
        if len(candidates) < 2:
            continue
        seen: dict[str, dict] = {}
        for entry in candidates:
            found = digest(entry["id"])
            if found in seen:
                dupes.append((entry, seen[found]))
            else:
                seen[found] = entry
    return dupes


def reference_nodes(record: dict) -> set[str]:
    """The node ids this character's `REF#` rows point at.

    Read before anything is deleted, so `dedupe` can detach the row of an image
    it is about to destroy. A row naming a node that no longer exists is the one
    dangling this model can still produce, and it is produced by deleting bytes
    rather than by moving them.
    """
    return {entry["node"] for entry in entities.reference_entries(record["id"])}


def find_in_pool(record: dict, pool: str, token: str) -> dict:
    """A node in one pool, from a node id or a name a person typed.

    `<group>/<name>` reaches one level down, which is how `reference/face/…` is
    addressed; a bare name is looked for in the pool root and then in each
    subfolder. An id skips all of it and is what a script should pass.
    """
    if token.startswith("node-"):
        try:
            return store.node(token)
        except api.NotFound:
            die(f"no such node: {token}")
    token = token.strip().lstrip("/")
    folder, _, name = token.rpartition("/")
    if folder:
        found = next((e for e in images(record, pool, folder) if e["name"] == name), None)
        if found is None:
            die(f"{token!r} is not in {record['slug']}/{pool}/")
        return found

    hits = [e for e in images(record, pool) if e["name"] == name]
    root = pool_folder(record, pool)
    for child in store.children_of(root["id"]):
        if child.get("kind") == "folder":
            hits += [e for e in images(record, pool, child["name"]) if e["name"] == name]
    if not hits:
        have = [e["name"] for e in images(record, pool)]
        die(f"{token!r} is not in {pool}/ (have: {', '.join(have[:12]) or 'nothing'})")
    if len(hits) > 1:
        die(f"{token!r} matches {len(hits)} files in {pool}/ — name the node id or "
            "the <group>/<name> path")
    return hits[0]


# --- commands -------------------------------------------------------------

@click.group(help=__doc__)
def main():
    pass


@main.command("dedupe")
@click.argument("name", required=True)
@click.option("--apply", is_flag=True, help="Actually make the changes.")
@click.option("--group", help="A subfolder of the pool (default: the root of the pool).")
@click.option("--pool", type=click.Choice(POOL_CHOICES), default='reference')
def cmd_dedupe(name, apply, group, pool):
    """Delete byte-identical copies, keeping the first of each.

    **The one command here that destroys bytes**, which is why it is also the
    one that touches the reference index: a `REF#` row naming a node that has
    been deleted is the only dangling this model can still produce, so the row
    is detached in the same act. A move cannot produce one — the row names the
    node, and the node survives the move.
    """
    record = resolve(name)
    entries = images(record, pool, group)
    dupes = duplicate_pairs(entries)
    if not dupes:
        print(f"no exact duplicates in {pool}/ ({len(entries)} image(s))")
        return
    attached = reference_nodes(record)
    print(f"DELETE {len(dupes)} exact duplicate(s) from {pool}/:")
    for entry, keeper in dupes:
        mark = "  [is a reference — its row is detached too]" if entry["id"] in attached else ""
        print(f"    {entry['name']:<40} (identical to {keeper['name']}){mark}")
    if not apply:
        print("\nDRY RUN — nothing changed")
        return
    for entry, _keeper in dupes:
        if entry["id"] in attached:
            entities.delete_reference(record["id"], entry["id"])
    store.delete_nodes([entry["id"] for entry, _ in dupes])
    print("\nAPPLIED")


@main.command("drop", epilog=("\n\nArguments:\n  FILES  Node ids, or names inside the pool "
                             "(e.g. current/shot.jpg)."))
@click.argument("name", required=True)
@click.argument("files", nargs=-1, required=True)
@click.option("--apply", is_flag=True, help="Actually destroy them.")
@click.option("--pool", type=click.Choice(POOL_CHOICES), default='archive')
def cmd_drop(name, files, apply, pool):
    """Destroy named files. **The only command here that deletes on request.**

    Everything else in this module relocates: an image leaving a pool is moved,
    and `dedupe` destroys bytes only where a byte-identical copy is already
    waiting where the source was going. That rule is good and stays — it is why
    a mis-click cannot lose the only copy of something.

    What it did not cover is a file that should never have been uploaded. There
    was no way to remove one at all: it could be moved between pools forever and
    never destroyed, so a mistaken upload was permanent and `archive/` slowly
    became a place things went to not be deleted. This is the deliberate escape
    hatch, and it is deliberately awkward — every file named explicitly, a dry
    run by default, and no globbing.

    **It refuses a reference rather than detaching one.** `dedupe` detaches in
    the same act because it is removing a duplicate of something the character
    still has; dropping is removing the thing itself, and whether a character
    still IS what that image shows is a separate decision that hard rule #2b
    puts in a person's hands. `studio character detach` first, then drop.

    The prod bucket is versioned and neither the API role nor a developer's own
    commands hold `s3:DeleteObjectVersion`, so what this destroys there is a
    recoverable tombstone rather than the bytes. That is a backstop, not a
    licence: nothing in the catalog points at it afterwards.
    """
    record = resolve(name)
    entries = [find_in_pool(record, pool, token) for token in files]
    attached = reference_nodes(record)
    blocked = [e for e in entries if e["id"] in attached]
    if blocked:
        die("refusing to destroy image(s) a REF# row still names:\n"
            + "\n".join(f"      {e['name']}  ({e['id']})" for e in blocked)
            + f"\n       Detach first: studio character detach {record['slug']} "
            + " ".join(e["id"] for e in blocked))

    print(f"DESTROY {len(entries)} file(s) from {pool}/:")
    for entry in entries:
        size = int(entry.get("size") or 0)
        print(f"    {entry['name']:<40} {entry['id']}  {size // 1024} KB")
    if not apply:
        print("\nDRY RUN — nothing changed")
        return
    store.delete_nodes([entry["id"] for entry in entries])
    print("\nAPPLIED")


@main.command("move", epilog=("\n\nArguments:\n  FILE  A node id, or a name inside the source "
                              "pool (e.g. face/front-neutral.webp)."))
@click.argument("name", required=True)
@click.argument("file", required=True)
@click.option("--apply", is_flag=True)
# The parameter names are what Click passes to the callback, so they must match
# the signature below — `--from`/`--to` alone would arrive as `from_`/`to` and the
# call would fail with a TypeError. Nothing catches that until the command is run
# WITH arguments: invoking it bare exits on usage first, which is why this
# survived the argparse port.
@click.option("--from", "src_pool", type=click.Choice(POOL_CHOICES), default='reference')
@click.option("--to", "dst_pool", type=click.Choice(POOL_CHOICES), default='archive')
@click.option("--to-group", "dst_group", default=None,
              help="A subfolder of the destination pool, created if absent.")
def cmd_move(name, file, apply, src_pool, dst_pool, dst_group):
    """Move one image between pools. **A reparent: no object is written.**

    Unless a byte-identical copy is already waiting in the destination, in which
    case the source is deleted and nothing arrives. That second case is the only
    one that destroys bytes.

    **Moving out of `reference/` does not stop an image being a reference.** It
    used to, because reference-ness was a location; it is a `REF#` row now, and
    a row that names this node keeps naming it wherever the file goes. Demoting
    is `studio character detach`, which is a statement about identity rather
    than about a folder — and keeping the two apart is the whole point of the
    change.

    `--to-group` puts the file in a SUBFOLDER of the destination pool, so a pool
    a person has organised into subfolders can be reorganised. Without it the
    destination was always a pool root, and `--from seed --to seed` — the shape
    of every "it is in the wrong subfolder" fix — moved the file OUT of its
    subfolder and into the root beside the originals.
    """
    record = resolve(name)
    entry = find_in_pool(record, src_pool, file)
    destination = pool_folder(record, dst_pool)
    # The FILE argument has always reached into a subfolder (`face/front.webp`);
    # the destination could not, so a file in `seed/current/` could only be moved
    # to the root of some pool. Organising a pool into subfolders was therefore
    # a one-way trip — the way in existed and the way back did not, and putting
    # something in the wrong subfolder left it there.
    if dst_group:
        destination = store.ensure_child_folder(destination["id"], dst_group)
    where = f"{dst_pool}/{dst_group}" if dst_group else dst_pool
    print(f"MOVE {src_pool}/{entry['name']} -> {where}/{entry['name']}")

    # Same size first, for the reason `duplicate_pairs` gives.
    size = int(entry.get("size") or 0)
    candidates = [e for e in images(record, dst_pool, dst_group)
                  if int(e.get("size") or 0) == size]
    duplicate = bool(candidates) and digest(entry["id"]) in {digest(e["id"]) for e in candidates}
    if duplicate:
        print(f"    a byte-identical copy is already in {where}/ — only removing the source")

    if entry["id"] in reference_nodes(record):
        if duplicate:
            print("    NOTE: it is a reference and its bytes are about to go. Its REF# row "
                  f"would name a missing node — detach it first:\n"
                  f"      studio character detach {record['slug']} {entry['id']}")
        else:
            print("    it is a reference; the REF# row names the node and follows it")

    if not apply:
        print("\nDRY RUN — nothing changed")
        return
    if duplicate:
        store.delete_nodes([entry["id"]])
    else:
        store.reparent_node(entry["id"], destination["id"])
    print("\nAPPLIED")


@main.command("groups")
@click.argument("name", required=True)
def cmd_groups(name):
    """What the reference index holds, group by group, against the engine caps.

    **Off `GET /api/characters/<id>/references`'s `counts`, not off the tree.**
    It used to list the subfolders of `reference/` and count the files in each,
    which made a group a folder and a folder a group — so an image filed in the
    wrong place was in the wrong group, and one filed loose was in no group at
    all. A group is an attribute of a row; the folders are just folders.
    """
    record = resolve(name)
    counts = entities.references(record["id"]).get("counts") or {}
    for group, number in sorted(counts.items()):
        print(f"{group:<16} {number:>4}")
    total = sum(counts.values())
    print(f"{'TOTAL':<16} {total:>4}")
    lowest = min(ENGINE_CAPS.values())
    if total > lowest:
        print(f"\nthis character has more references than any model takes at once "
              f"({', '.join(f'{e} {c}' for e, c in sorted(ENGINE_CAPS.items()))}).\n"
              f"That is expected — pick a subset:\n"
              f"  studio character refs {record['slug']}\n"
              f"  studio character default-set {record['slug']} <node> <node> …", file=sys.stderr)
