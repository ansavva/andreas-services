"""`studio curate` — maintain a character's image pools: dedupe, renumber, move.

Curating by hand goes wrong the same ways every time: duplicates creep in under
different names, numbering develops holes, and "replacing" an image quietly
destroys the only copy. This does those operations safely, and keeps the bible's
reference index in step so a written description survives them.

Four pools, per `studio-media-character`:

    reference/   generated character imagery, in purpose subfolders
                 (face/, body/, wardrobe/ …), numbered within each group and
                 DESCRIBED in the bible's `references:` index.
    corpus/      collected material — uploads, keeper clips.
    seed/        the founding real-world source photos.
    archive/     retired material; never referenced unless asked for by name.

Only `reference/` is numbered, because only `reference/` is cited by slot.
Everywhere else the basename is kept, since renaming a source photo throws away
whatever its filename recorded.

WHAT IS NO LONGER HERE
----------------------
`set-refs` rebuilt `reference/` from chosen numbers, because the folder WAS the
set that got sent. It is not any more: the bible's `default_set:` names what is
sent, so choosing is `studio character default-set`, and demoting an image is
`studio curate move … --to archive`. Choosing no longer means moving objects.

Nothing is deleted outright: an image leaving a pool is preserved into the
destination first, and skipped only when a byte-identical copy is already there.
Every command is a DRY RUN unless you pass --apply.

  studio curate dedupe <name> --pool reference
  studio curate renumber <name> --group face
  studio curate move face/<name>_face_3.png <name> --from reference --to archive
  studio curate regroup <name> face <name>_3.jpg <name>_4.jpg --apply

NOTHING HERE MOVES BYTES ANY MORE
---------------------------------
Every operation in this module used to be a `CopyObject` plus a
`DeleteObject`, because S3 has no rename: the key IS the location, so renumbering
`<name>_3.png` to `<name>_1.png` meant writing a new object and destroying the
old one. Under the catalog a name is a column. `renumber` and `regroup` are now
`PATCH /api/nodes/<id>` — a row update each, **zero objects written**, and the
blob keeps its key, its bytes and its node id.

`dedupe` still reads bytes, because comparing them is the point. It reads fewer
than it did: the catalog records each file's size, so only same-size files can
be identical and only those are hashed.

MOVING AN IMAGE STILL MOVES ITS RECORDS
---------------------------------------
**And this is the half of #306 that could not be done.** The plan was that
`rewrite.py`'s move path would go: if nothing moves, nothing dangles.

It does not go, because a record does not name a node — it names a **path**.
`runs.check_bindings` validates against `characters/`, `projects/`,
`phrasebook/` and `config/`, and `resolve_output_keys` builds a path from a
folder and a name. So renaming `face/<name>_3.png` to `face/<name>_1.png` leaves
every run that cited the first one pointing at a path that no longer resolves —
exactly as a `CopyObject` did, for a different reason.

What retires this is records naming **node ids**, which survive a rename by
construction. That is a real change and nobody has filed it: it moves the
binding invariant, `resolve_output_keys`, and the vocabulary every `SKILL.md`
is written in. Until then `regroup`, `renumber` and `move` carry the records
along, and skipping that step is still what left 69 records dangling.
"""
from __future__ import annotations

import hashlib
import os
import sys

import click

from studio_pipeline.adapters import api, store
from studio_pipeline.domain import rewrite
from studio_pipeline.domain.characters import (
    check_name,
    group_prefix,
    pool_folder,
    ref_root,
    sync_index,
)
from studio_pipeline.errors import die

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
# The caps are prose-only in every model's schema (maxItems is null), so they are
# maintained here by hand. The lowest one binds a set that is sent in full.
ENGINE_CAPS = {"kling": 7, "seedance": 9, "nano-banana": 14}


def folder(name: str, pool: str, group: str | None = None) -> str:
    return pool_folder(name, pool) + (f"/{group}" if group else "")


def pool_entries(name: str, pool: str, group: str | None = None) -> list[dict]:
    """Image entries in a pool (optionally one reference subfolder), in order.

    The "a subfolder is its own group" filter is gone with the recursive listing
    that made it necessary — `store.files` is one level deep, so the images in
    `reference/face/` are simply not among `reference/`'s children.
    """
    base = folder(name, pool, group)
    return [{**e, "path": f"{base}/{e['name']}"} for e in store.files(base)
            if os.path.splitext(e["name"])[1].lower() in IMG_EXTS]


def pool_keys(name: str, pool: str, group: str | None = None) -> list[str]:
    """Just the paths — what the callers that only print them want."""
    return [e["path"] for e in pool_entries(name, pool, group)]


def groups(name: str) -> list[str]:
    """The purpose subfolders that exist inside reference/."""
    return sorted(
        e["name"] for e in store.children_or_empty(pool_folder(name, "reference"))
        if e.get("kind") == "folder" and e.get("name")
    )


def digest(path: str) -> str:
    """Content hash of one image. Only ever called on same-size candidates."""
    return hashlib.md5(store.read(path)).hexdigest()


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
            found = digest(entry["path"])
            if found in seen:
                dupes.append((entry, seen[found]))
            else:
                seen[found] = entry
    return dupes


def rename_node(entry: dict, new_name: str) -> None:
    """Rename one node in place. **No object is written.**"""
    api.patch(f"/api/nodes/{entry['id']}", {"name": new_name})


def move_node(entry: dict, parent_id: str) -> None:
    """Reparent one node. **No object is written.**"""
    api.patch(f"/api/nodes/{entry['id']}", {"parent": parent_id})


def delete_node(entry: dict) -> None:
    """Remove a node and its blob. The one operation here that destroys bytes."""
    api.delete(f"/api/nodes/{entry['id']}")


def rel_to_reference(name: str, key: str) -> str | None:
    """A reference key as the index records it, or None if it is elsewhere."""
    root = ref_root(name)
    return key[len(root):] if key.startswith(root) else None


def apply_index(name: str, moves: list[tuple[str, str]], apply: bool) -> None:
    """Carry descriptions across a set of reference renames.

    The rename map is passed rather than letting the index re-derive itself,
    because a re-derived index cannot tell a renamed image from a new one and
    would silently blank the description it had.
    """
    rename = {}
    for src, dst in moves:
        a, b = rel_to_reference(name, src), rel_to_reference(name, dst)
        if a and b:
            rename[a] = b
    if apply:
        report = sync_index(name, rename_map=rename, apply=True)
        if report["missing"]:
            print(f"  index: {len(report['missing'])} entry(ies) now point at a missing "
                  f"file and are flagged, not dropped: {', '.join(report['missing'][:4])}")


def ordered_moves(moves: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Order renames so a destination never clobbers a source not yet moved."""
    pending, plan = list(moves), []
    while pending:
        srcs = {s for s, _ in pending}
        safe = [m for m in pending if m[1] not in srcs]
        if not safe:  # cycle — break it through a temp key
            s, d = pending[0]
            tmp = s + ".tmp-curate"
            plan.append((s, tmp))
            pending[0] = (tmp, d)
            continue
        for m in safe:
            plan.append(m)
            pending.remove(m)
    return plan


# --- commands -------------------------------------------------------------

@click.group(help=__doc__)
def main():
    pass


@main.command("dedupe")
@click.argument("name", required=True)
@click.option("--apply", is_flag=True, help="Actually make the changes.")
@click.option("--group", help="A reference subfolder (default: the root of the pool).")
@click.option("--pool", type=click.Choice(["archive", "corpus", "reference", "seed"]), default='reference')
def cmd_dedupe(name, apply, group, pool):
    check_name(name)
    entries = pool_entries(name, pool, group)
    dupes = duplicate_pairs(entries)
    if not dupes:
        print(f"no exact duplicates in {pool}/ ({len(entries)} image(s))")
        return
    print(f"DELETE {len(dupes)} exact duplicate(s) from {pool}/:")
    for entry, keeper in dupes:
        print(f"    {entry['name']:<40} (identical to {keeper['name']})")
    if apply:
        for entry, _ in dupes:
            delete_node(entry)
        if pool == "reference":
            sync_index(name, apply=True)
        print("\nAPPLIED")
    else:
        print("\nDRY RUN — nothing changed")


@main.command("renumber")
@click.argument("name", required=True)
@click.option("--apply", is_flag=True)
@click.option("--group", help="A reference subfolder (default: the root of reference/).")
def cmd_renumber(name, apply, group):
    """Close holes in one reference group's numbering.

    **A row update per image, and no object written.** This was a copy and a
    delete per file, because an S3 key is a location; here the name is a column
    and the blob does not know it changed. `ordered_moves` still applies — a
    catalog folder refuses a duplicate name exactly as a bucket would overwrite
    one, so `1->2, 2->1` still has to go through a temporary.
    """
    check_name(name)
    entries = pool_entries(name, "reference", group)
    ordered = sorted(entries, key=lambda e: store.natural_key(e["name"]))
    prefix = group_prefix(name, group)
    dest = folder(name, "reference", group)
    by_path = {e["path"]: e for e in ordered}
    moves = []
    for i, entry in enumerate(ordered, start=1):
        ext = os.path.splitext(entry["name"])[1].lower()
        target = f"{dest}/{prefix}{i}{ext}"
        if entry["path"] != target:
            moves.append((entry["path"], target))
    if not moves:
        print(f"{dest}/ is already contiguous ({len(ordered)} image(s))")
        return
    plan = ordered_moves(moves)
    print(f"RENAME {len(plan)} file(s) in {dest}/:")
    for src, dst in plan:
        print(f"    {os.path.basename(src):<44} -> {os.path.basename(dst)}")
    print(f"\nresult: {len(ordered)} image(s), 1..{len(ordered)}")
    if apply:
        for src, dst in plan:
            entry = by_path[src]
            rename_node(entry, os.path.basename(dst))
            # The plan renames in sequence and a temporary is renamed again, so
            # the node has to be findable under the name it now carries.
            entry["path"] = dst
            by_path[dst] = entry
        apply_index(name, moves, True)
        print("APPLIED")
    else:
        print("DRY RUN — nothing changed")


@main.command("move", epilog="\n\nArguments:\n  FILE  Path inside the source pool, e.g. face/<name>_face_3.png")
@click.argument("file", required=True)
@click.argument("name", required=True)
@click.option("--apply", is_flag=True)
# The parameter names are what Click passes to the callback, so they must match
# the signature below — `--from`/`--to` alone would arrive as `from_`/`to` and the
# call would fail with a TypeError. Nothing catches that until the command is run
# WITH arguments: invoking it bare exits on usage first, which is why this
# survived the argparse port.
@click.option("--from", "src_pool", type=click.Choice(["archive", "corpus", "reference", "seed"]), default='reference')
@click.option("--to", "dst_pool", type=click.Choice(["archive", "corpus", "reference", "seed"]), default='archive')
def cmd_move(file, name, apply, src_pool, dst_pool):
    """Move one image between pools, by its path inside the source pool.

    **A reparent, not a copy and a delete** — unless a byte-identical copy is
    already waiting in the destination, in which case the source is deleted and
    nothing arrives. That second case is the only one that destroys bytes, and
    it is the one whose records cannot follow anywhere.
    """
    check_name(name)
    src_folder = folder(name, src_pool)
    path = f"{src_folder}/{file.strip().lstrip('/')}"
    try:
        entry = store.resolve(path)
    except api.NotFound:
        have = [e["name"] for e in pool_entries(name, src_pool)]
        die(f"{file!r} is not in {src_pool}/ (have: {', '.join(have[:12]) or 'nothing'})")

    dst_folder = folder(name, dst_pool)
    dst = f"{dst_folder}/{os.path.basename(file)}"
    print(f"MOVE {src_pool}/{file} -> {dst_pool}/{os.path.basename(file)}")

    # Same size first, for the reason `duplicate_pairs` gives.
    size = int(entry.get("size") or 0)
    candidates = [e for e in pool_entries(name, dst_pool) if int(e.get("size") or 0) == size]
    if candidates and digest(path) in {digest(e["path"]) for e in candidates}:
        print(f"    a byte-identical copy is already in {dst_pool}/ — only removing the source")
        dst = None

    # The records that cite this image follow it, or they are left naming a
    # path that is about to stop resolving. See the module docstring — a rename
    # does not save them, because a record names a path and not a node.
    touched = rewrite.apply_moves({path: dst} if dst else {}, apply=apply)
    if touched:
        print(f"  {'rewrote' if apply else 'would rewrite'} {len(touched)} record(s) "
              f"citing it")
    elif not dst:
        print("  NOTE: the source is only being removed, so any record citing it will "
              "dangle — check with `studio runs find` first if that matters")

    if apply:
        if dst:
            move_node(entry, store.folder(dst_folder)["id"])
        else:
            delete_node(entry)
        if "reference" in (src_pool, dst_pool):
            sync_index(name, apply=True)
        if src_pool == "reference":
            print("APPLIED — the index entry is flagged missing; check `default_set` "
                  "still names only images that exist")
        else:
            print("APPLIED")
    else:
        print("DRY RUN — nothing changed")


@main.command("regroup", epilog="\n\nArguments:\n  FILES  Paths inside reference/.\n  GROUP  face, body, wardrobe, frame, …")
@click.argument("files", nargs=-1, required=True)
@click.argument("group", required=True)
@click.argument("name", required=True)
@click.option("--apply", is_flag=True)
def cmd_regroup(files, group, name, apply):
    """Move reference images into a purpose subfolder, records and all.

    Basenames are kept: only the parent changes. Renaming as well would churn
    every recorded path for no gain, and the group is already in the path.
    """
    check_name(name)
    root = ref_root(name)
    moves: list[tuple[str, str]] = []
    nodes: dict[str, dict] = {}
    for f in files:
        f = f.strip().lstrip("/")
        src = root + f
        try:
            nodes[src] = store.resolve(src)
        except api.NotFound:
            die(f"{f!r} is not in {name}'s reference/")
        dst = root + f"{group}/{os.path.basename(f)}"
        if src != dst:
            moves.append((src, dst))

    if not moves:
        print(f"nothing to move — all {len(files)} already in {group}/")
        return

    print(f"MOVE {len(moves)} image(s) into reference/{group}/:")
    for s, d in moves:
        print(f"    {s[len(root):]:<28} -> {d[len(root):]}")

    # Every run, scene and chain that cited these keys is rewritten in the same
    # operation. Moving reference images without this is what left 69 records
    # pointing at keys that no longer existed.
    mapping = dict(moves)
    touched = rewrite.apply_moves(mapping, apply=apply)
    if touched:
        print(f"\n{'REWROTE' if apply else 'would rewrite'} {len(touched)} record(s) "
              f"that cite these images:")
        for k, n in list(touched.items())[:8]:
            print(f"    {k}  ({n} reference(s))")
        if len(touched) > 8:
            print(f"    … and {len(touched) - 8} more")
    else:
        print("\nno run, scene or chain cites these images")

    if apply:
        parent = store.folder(f"{root}{group}")["id"]
        for src, _dst in moves:
            move_node(nodes[src], parent)
        apply_index(name, moves, True)
        print("\nAPPLIED")
    else:
        print("\nDRY RUN — nothing changed")


@main.command("groups")
@click.argument("name", required=True)
def cmd_groups(name):
    """What is in reference/, group by group, against the engine caps."""
    check_name(name)
    root = ref_root(name)
    loose = pool_keys(name, "reference")
    rows = [("(root)", len(loose))] + [(g, len(pool_keys(name, "reference", g)))
                                       for g in groups(name)]
    total = sum(n for _g, n in rows)
    for g, n in rows:
        if n:
            print(f"{g:<16} {n:>4}")
    print(f"{'TOTAL':<16} {total:>4}")
    lowest = min(ENGINE_CAPS.values())
    if total > lowest:
        print(f"\nreference/ holds more than any model takes at once "
              f"({', '.join(f'{e} {c}' for e, c in sorted(ENGINE_CAPS.items()))}).\n"
              f"That is expected — pick a subset:\n"
              f"  studio character refs {name} --describe\n"
              f"  studio character default-set {name} --set <file> <file> …", file=sys.stderr)
    _ = root
