# /// script
# requires-python = ">=3.13"
# dependencies = ["boto3", "pyyaml"]
# ///
"""curate.py — maintain a character's image pools: dedupe, renumber, move.

Curating by hand goes wrong the same ways every time: duplicates creep in under
different names, numbering develops holes, and "replacing" an image quietly
destroys the only copy. This does those operations safely, and keeps the bible's
reference index in step so a written description survives them.

Four pools, per `studio-character`:

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
sent, so choosing is `character.py default-set`, and demoting an image is
`curate.py move … --to archive`. Choosing no longer means moving objects.

Nothing is deleted outright: an image leaving a pool is preserved into the
destination first, and skipped only when a byte-identical copy is already there.
Every command is a DRY RUN unless you pass --apply.

  uv run curate.py dedupe <name> --pool reference
  uv run curate.py renumber <name> --group face
  uv run curate.py move <name> face/<name>_face_3.png --from reference --to archive
  uv run curate.py regroup <name> face <name>_3.jpg <name>_4.jpg --apply

MOVING AN IMAGE MOVES ITS RECORDS TOO
-------------------------------------
Run records, scene manifests and chains all store S3 keys, so moving an object
invalidates every document that cited it. `regroup` and `move` rewrite those
documents in the same operation (see s3/scripts/rewrite.py). Curating without
that step is what left 69 records pointing at keys that no longer existed.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from character import (  # noqa: E402
    check_name, group_prefix, pool_folder, ref_root, sync_index,
)

_S3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "s3", "scripts")
sys.path.insert(0, os.path.abspath(_S3))
import paths as P  # noqa: E402
import rewrite  # noqa: E402
import s3_common as s3c  # noqa: E402

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}
# The caps are prose-only in every model's schema (maxItems is null), so they are
# maintained here by hand. The lowest one binds a set that is sent in full.
ENGINE_CAPS = {"kling": 7, "seedance": 9, "nano-banana": 14}


def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def folder(name: str, pool: str, group: str | None = None) -> str:
    return pool_folder(name, pool) + (f"/{group}" if group else "")


def pool_keys(s3, name: str, pool: str, group: str | None = None) -> list[str]:
    """Image keys in a pool (optionally one reference subfolder)."""
    base = folder(name, pool, group)
    root = s3c.key(base) + "/"
    keys = [k for k in s3c.list_keys(s3, base)
            if os.path.splitext(k)[1].lower() in IMG_EXTS]
    if pool == "reference" and group is None:
        keys = [k for k in keys if "/" not in k[len(root):]]  # a subfolder is its own group
    return keys


def groups(s3, name: str) -> list[str]:
    """The purpose subfolders that exist inside reference/."""
    root = ref_root(name)
    out = set()
    for k in s3c.list_keys(s3, pool_folder(name, "reference")):
        rest = k[len(root):]
        if "/" in rest:
            out.add(rest.split("/", 1)[0])
    return sorted(out)


def md5(s3, key: str) -> str:
    h = hashlib.md5()
    body = s3.get_object(Bucket=s3c.BUCKET, Key=key)["Body"]
    for chunk in iter(lambda: body.read(1 << 20), b""):
        h.update(chunk)
    return h.hexdigest()


def copy(s3, src: str, dst: str) -> None:
    s3.copy_object(Bucket=s3c.BUCKET, CopySource={"Bucket": s3c.BUCKET, "Key": src},
                   Key=dst, MetadataDirective="COPY")


def rel_to_reference(name: str, key: str) -> str | None:
    """A reference key as the index records it, or None if it is elsewhere."""
    root = ref_root(name)
    return key[len(root):] if key.startswith(root) else None


def apply_index(s3, name: str, moves: list[tuple[str, str]], apply: bool) -> None:
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
        report = sync_index(s3, name, rename_map=rename, apply=True)
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

def cmd_dedupe(args, s3) -> None:
    keys = pool_keys(s3, args.name, args.pool, args.group)
    keys.sort(key=lambda k: s3c.natural_key(os.path.basename(k)))
    seen, dupes = {}, []
    for k in keys:
        h = md5(s3, k)
        if h in seen:
            dupes.append((k, seen[h]))
        else:
            seen[h] = k
    if not dupes:
        print(f"no exact duplicates in {args.pool}/ ({len(keys)} image(s))")
        return
    print(f"DELETE {len(dupes)} exact duplicate(s) from {args.pool}/:")
    for k, keeper in dupes:
        print(f"    {os.path.basename(k):<40} (identical to {os.path.basename(keeper)})")
    if args.apply:
        for k, _ in dupes:
            s3.delete_object(Bucket=s3c.BUCKET, Key=k)
        if args.pool == "reference":
            sync_index(s3, args.name, apply=True)
        print("\nAPPLIED")
    else:
        print("\nDRY RUN — nothing changed")


def cmd_renumber(args, s3) -> None:
    """Close holes in one reference group's numbering."""
    keys = pool_keys(s3, args.name, "reference", args.group)
    ordered = sorted(keys, key=lambda k: s3c.natural_key(os.path.basename(k)))
    prefix = group_prefix(args.name, args.group)
    dest = folder(args.name, "reference", args.group)
    moves = []
    for i, src in enumerate(ordered, start=1):
        ext = os.path.splitext(src)[1].lower()
        dst = s3c.key(f"{dest}/{prefix}{i}{ext}")
        if src != dst:
            moves.append((src, dst))
    if not moves:
        print(f"{dest}/ is already contiguous ({len(ordered)} image(s))")
        return
    plan = ordered_moves(moves)
    print(f"RENAME {len(plan)} file(s) in {dest}/:")
    for s, d in plan:
        print(f"    {os.path.basename(s):<44} -> {os.path.basename(d)}")
    print(f"\nresult: {len(ordered)} image(s), 1..{len(ordered)}")
    if args.apply:
        for src, dst in plan:
            copy(s3, src, dst)
            s3.delete_object(Bucket=s3c.BUCKET, Key=src)
        apply_index(s3, args.name, moves, True)
        print("APPLIED")
    else:
        print("DRY RUN — nothing changed")


def cmd_move(args, s3) -> None:
    """Move one image between pools, by its path inside the source pool."""
    src_root = s3c.key(folder(args.name, args.src_pool)) + "/"
    key = src_root + args.file.lstrip("/")
    try:
        s3.head_object(Bucket=s3c.BUCKET, Key=key)
    except Exception:  # noqa: BLE001
        have = [k[len(src_root):] for k in pool_keys(s3, args.name, args.src_pool)]
        die(f"{args.file!r} is not in {args.src_pool}/ (have: {', '.join(have[:12]) or 'nothing'})")

    dst_folder = folder(args.name, args.dst_pool)
    dst = s3c.key(f"{dst_folder}/{os.path.basename(args.file)}")
    print(f"MOVE {args.src_pool}/{args.file} -> {args.dst_pool}/{os.path.basename(args.file)}")

    existing = {md5(s3, k) for k in pool_keys(s3, args.name, args.dst_pool)}
    if md5(s3, key) in existing:
        print(f"    a byte-identical copy is already in {args.dst_pool}/ — only removing the source")
        dst = None

    # The records that cite this image follow it, or they are left pointing at
    # a key that is about to stop existing.
    touched = rewrite.apply_moves(s3, {key: dst} if dst else {}, apply=args.apply)
    if touched:
        print(f"  {'rewrote' if args.apply else 'would rewrite'} {len(touched)} record(s) "
              f"citing it")
    elif not dst:
        print("  NOTE: the source is only being removed, so any record citing it will "
              "dangle — check with `runs.py find` first if that matters")

    if args.apply:
        if dst:
            copy(s3, key, dst)
        s3.delete_object(Bucket=s3c.BUCKET, Key=key)
        if "reference" in (args.src_pool, args.dst_pool):
            sync_index(s3, args.name, apply=True)
        if args.src_pool == "reference":
            print("APPLIED — the index entry is flagged missing; check `default_set` "
                  "still names only images that exist")
        else:
            print("APPLIED")
    else:
        print("DRY RUN — nothing changed")


def cmd_regroup(args, s3) -> None:
    """Move reference images into a purpose subfolder, records and all.

    Basenames are kept: only the path changes. Renaming as well would churn
    every recorded key for no gain, and the group is already in the path.
    """
    root = ref_root(args.name)
    moves: list[tuple[str, str]] = []
    for f in args.files:
        f = f.strip().lstrip("/")
        src = root + f
        try:
            s3.head_object(Bucket=s3c.BUCKET, Key=src)
        except Exception:  # noqa: BLE001
            die(f"{f!r} is not in {args.name}'s reference/")
        dst = root + f"{args.group}/{os.path.basename(f)}"
        if src != dst:
            moves.append((src, dst))

    if not moves:
        print(f"nothing to move — all {len(args.files)} already in {args.group}/")
        return

    print(f"MOVE {len(moves)} image(s) into reference/{args.group}/:")
    for s, d in moves:
        print(f"    {s[len(root):]:<28} -> {d[len(root):]}")

    # Every run, scene and chain that cited these keys is rewritten in the same
    # operation. Moving reference images without this is what left 69 records
    # pointing at keys that no longer existed.
    mapping = dict(moves)
    touched = rewrite.apply_moves(s3, mapping, apply=args.apply)
    if touched:
        print(f"\n{'REWROTE' if args.apply else 'would rewrite'} {len(touched)} record(s) "
              f"that cite these images:")
        for k, n in list(touched.items())[:8]:
            print(f"    {k}  ({n} reference(s))")
        if len(touched) > 8:
            print(f"    … and {len(touched) - 8} more")
    else:
        print("\nno run, scene or chain cites these images")

    if args.apply:
        for src, dst in moves:
            copy(s3, src, dst)
            s3.delete_object(Bucket=s3c.BUCKET, Key=src)
        apply_index(s3, args.name, moves, True)
        print("\nAPPLIED")
    else:
        print("\nDRY RUN — nothing changed")


def cmd_groups(args, s3) -> None:
    """What is in reference/, group by group, against the engine caps."""
    root = ref_root(args.name)
    loose = pool_keys(s3, args.name, "reference")
    rows = [("(root)", len(loose))] + [(g, len(pool_keys(s3, args.name, "reference", g)))
                                       for g in groups(s3, args.name)]
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
              f"  character.py refs {args.name} --describe\n"
              f"  character.py default-set {args.name} --set <file> <file> …", file=sys.stderr)
    _ = root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dedupe", help="Remove byte-identical duplicates.")
    p.add_argument("name")
    p.add_argument("--pool", choices=sorted(P.CHAR_POOLS), default="reference")
    p.add_argument("--group", help="A reference subfolder (default: the root of the pool).")
    p.add_argument("--apply", action="store_true", help="Actually make the changes.")
    p.set_defaults(func=cmd_dedupe)

    p = sub.add_parser("renumber", help="Renumber one reference group to a contiguous 1..N.")
    p.add_argument("name")
    p.add_argument("--group", help="A reference subfolder (default: the root of reference/).")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_renumber)

    p = sub.add_parser("move", help="Move one image between pools (preserved, never deleted outright).")
    p.add_argument("name")
    p.add_argument("file", help="Path inside the source pool, e.g. face/<name>_face_3.png")
    p.add_argument("--from", dest="src_pool", choices=sorted(P.CHAR_POOLS), default="reference")
    p.add_argument("--to", dest="dst_pool", choices=sorted(P.CHAR_POOLS), default="archive")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("regroup", help="Move reference image(s) into a purpose subfolder.")
    p.add_argument("name")
    p.add_argument("group", help="face, body, wardrobe, scene, …")
    p.add_argument("files", nargs="+", help="Paths inside reference/.")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_regroup)

    p = sub.add_parser("groups", help="What reference/ holds, group by group.")
    p.add_argument("name")
    p.set_defaults(func=cmd_groups)

    args = ap.parse_args()
    check_name(args.name)
    args.func(args, s3c.client())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
