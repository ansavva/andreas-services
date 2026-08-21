"""Giving a character a new slug — objects, bible and records together.

A slug is a path segment, so changing it is not an edit: it is a move of every
object in the record plus a rewrite of every string that named the old one.
Doing that by hand is the failure `curate` and `rewrite` exist to prevent, which
is why it is a command rather than a runbook.

WHAT THIS COST, AND WHAT IT COSTS NOW
-------------------------------------
It was a `CopyObject` and a `DeleteObject` for every object under the character,
ordered so a half-finished run left a duplicate rather than a hole, plus a
zero-byte folder marker per folder that had to be carried or the app lost a
folder from its listing.

It is now **one `PATCH` per file whose basename carries the slug, and one more
for the character's folder.** No bytes move, no node changes identity, and there
are no folder markers because a folder is a row. The old ordering problem is
gone with it: a rename inside one parent cannot collide, because `<old>_` and
`<new>_` differ by construction.

`record_keys` and `rename_moves` survive, and only for the RECORDS. A run,
scene, movie or chain names this character by path, so every one of those paths
still changes and `rewrite` still has to carry them — see its module docstring
for why the catalog did not retire that. What they no longer drive is any object
operation.
"""
from __future__ import annotations

import os
import re

import click

from studio_pipeline.adapters import api, store
from studio_pipeline.domain import paths as P
from studio_pipeline.domain.characters.base import (
    PROFILE_FILE,
    check_name,
    die,
    profile_key,
)
from studio_pipeline.domain.characters.profile import (
    load_profile,
    remote_version,
    write_profile,
)

# --- rename ----------------------------------------------------------------
#
# A character's slug is a path segment, so changing it is not an edit — it is a
# move of every object in the record plus a rewrite of every string that named
# the old one. Doing that by hand is the failure `curate` and `rewrite` already
# exist to prevent, which is why it is a command rather than a runbook.

# A string the rename is willing to treat as a filename. Deliberately narrow:
# the bible is mostly prose, and prose that happens to mention the slug is not a
# path. A candidate must look like a path AND carry an extension.
FILEISH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def renamed_file(value: str, old: str, new: str) -> str | None:
    """`face/<old>_1.png` -> `face/<new>_1.png`, or None if it is not one."""
    if not isinstance(value, str) or not FILEISH_RE.match(value):
        return None
    head, _sep, base = value.rpartition("/")
    if not base.startswith(f"{old}_") or "." not in base:
        return None
    return (f"{head}/" if head else "") + f"{new}_{base[len(old) + 1:]}"


def rename_in_profile(node, old: str, new: str) -> int:
    """Swap the slug in every file-ish string, in place. Returns how many.

    Walks the whole bible rather than naming `references`, `default_set` and
    `corpus`: a key added later that stores a filename would otherwise be
    missed, and the miss would only show up as a dangling path months on.
    """
    changed = 0
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if (renamed := renamed_file(v, old, new)) is not None:
                node[k] = renamed
                changed += 1
            else:
                changed += rename_in_profile(v, old, new)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if (renamed := renamed_file(v, old, new)) is not None:
                node[i] = renamed
                changed += 1
            else:
                changed += rename_in_profile(v, old, new)
    return changed


def record_paths(name: str) -> list[str]:
    """Every file path under a character.

    **No folder markers, because there are none.** The S3 version had to keep
    the zero-byte marker objects — dropping one deleted a folder the app showed.
    A folder is a row now and moves with its parent, so there is nothing to
    carry.
    """
    return sorted(store.walk_files(P.character_prefix(name)), key=store.natural_key)


def rename_moves(keys: list[str], old: str, new: str) -> dict[str, str]:
    """{old path: new path} — the prefix changes, and so does a slugged basename.

    Pure, and now only feeds `rewrite`: nothing copies an object from the left
    of this map to the right. The catalog renames the folder and the basenames
    and every path below follows.
    """
    old_root = P.character_prefix(old) + "/"
    new_root = P.character_prefix(new) + "/"
    moves = {}
    for key in keys:
        head, _sep, base = key[len(old_root):].rpartition("/")
        if base.startswith(f"{old}_"):
            base = f"{new}_{base[len(old) + 1:]}"
        moves[key] = new_root + (f"{head}/" if head else "") + base
    return moves


def default_display_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


@click.command("rename")
@click.argument("old", required=True)
@click.argument("new", required=True)
@click.option("--apply", is_flag=True, help="Actually make the changes.")
@click.option("--display-name", "display_name",
              help="Prose name for the bible (default: title-cased NEW).")
def cmd_rename(old, new, apply, display_name):
    """Give a character a new slug: objects, bible and records together.

    Three things carry the old slug and all three have to move at once:

      * every node under `characters/<old>/`, whose basenames are prefixed
        with it (`<old>_face_1.png`) — renamed in place, no bytes moved;
      * the bible — `name`, `display_name`, and every path in `references`,
        `default_set` and any other file-ish string;
      * every run, scene, movie and chain document that cites one of those
        paths, or records the character by name.

    The index is FOLLOWED, never re-derived: `sync-refs` is not run, because
    reconciling here would add every undescribed image in `reference/` as a
    blank entry and drop `default_set` names — both separate decisions.

    One limit worth knowing: a record follows where it stores a path, or
    records the character in a `characters:`/`character:` field. A slug buried
    in a sentence — a prompt that names the character — is left alone, because
    editing prose is not a rename. So is a project that shares the name.

    DRY RUN unless --apply.
    """
    check_name(old)
    check_name(new)
    if old == new:
        die("OLD and NEW are the same name.")
    # Local, not module-level: curate imports this module, so importing it back
    # at the top would be a cycle.
    from studio_pipeline.domain import rewrite

    keys = record_paths(old)
    if not keys:
        have = P.list_characters()
        die(f"no character {old!r} (have: {', '.join(have) or 'none'}).")
    if store.exists(P.character_prefix(new)):
        die(f"{new!r} already exists — nothing here overwrites a record. "
            f"Pick another name, or move that one out of the way first.")

    display_name = display_name or default_display_name(new)
    moves = rename_moves(keys, old, new)
    profile_src = profile_key(old)
    if profile_src not in moves:
        die(f"{old} has no {PROFILE_FILE} — a record without a bible is not one this "
            f"command can move safely.")
    # The bible is REWRITTEN at the new key rather than copied: its contents
    # change in the same breath as its path.
    object_moves = {k: v for k, v in moves.items() if k != profile_src}

    print(f"{'RENAME' if apply else 'WOULD RENAME'} {old} -> {new}")
    print(f"  {len(object_moves)} object(s) under characters/{old}/ -> characters/{new}/")
    renamed = [(k, v) for k, v in object_moves.items()
               if os.path.basename(k) != os.path.basename(v)]
    for src, dst in renamed[:8]:
        print(f"    {os.path.basename(src):<34} -> {os.path.basename(dst)}")
    if len(renamed) > 8:
        print(f"    … and {len(renamed) - 8} more basename(s)")

    data = load_profile(old)
    version = remote_version(old)
    # Resolved BEFORE anything is renamed: after the folder moves, these paths
    # do not exist to resolve. The ids do not change, which is the whole reason
    # this is cheap.
    nodes = {path: store.resolve(path) for path in object_moves
             if os.path.basename(path) != os.path.basename(object_moves[path])}
    character_node = store.resolve(P.character_prefix(old))
    was_display = data.get("display_name")
    data["name"] = new
    data["display_name"] = display_name
    paths_changed = rename_in_profile(data, old, new)
    print(f"  bible: name -> {new}, display_name {was_display!r} -> {display_name!r}, "
          f"{paths_changed} path(s) rewritten")

    # Two passes, because records name a character two ways. The keys they cite
    # follow the objects; the name they record follows separately, since a
    # project may be called the same thing as a character and must not be
    # renamed along with it.
    cited = rewrite.apply_moves(moves, apply=apply)
    named = rewrite.rename_character(old, new, apply=apply)
    touched: dict[str, int] = dict(cited)
    for k, n in named.items():
        touched[k] = touched.get(k, 0) + n
    if touched:
        print(f"  {'rewrote' if apply else 'would rewrite'} {len(touched)} record(s):")
        for k, n in list(touched.items())[:8]:
            print(f"    {k}  ({n} reference(s))")
        if len(touched) > 8:
            print(f"    … and {len(touched) - 8} more")
    else:
        print("  no run, scene, movie or chain names this character")

    if not apply:
        print("\nDRY RUN — nothing changed")
        return

    # Checked before anything moves, not after: once the objects are under the new
    # prefix there is no clean way to refuse, and silently overwriting someone
    # else's edit is the failure `write_profile` exists to prevent.
    if remote_version(old) != version:
        die(f"{old}'s {PROFILE_FILE} changed since it was read — re-run to pick up the "
            f"new version rather than overwriting it. Nothing has moved.")

    # **Basenames first, then the folder.** Either order addresses the right
    # nodes — an id does not care what its path is — but doing the folder first
    # would make every message below name a path that no longer exists if a
    # later step failed. `ordered_moves` is not needed: a rename inside one
    # parent goes from `<old>_` to `<new>_`, which cannot collide.
    for path, node in nodes.items():
        api.patch(f"/api/nodes/{node['id']}", {"name": os.path.basename(moves[path])})
    api.patch(f"/api/nodes/{character_node['id']}", {"name": new})

    # The bible moved with the folder and is now at the new path; this rewrites
    # its CONTENTS. No version is passed: the one that was read belongs to a
    # path that no longer exists, and the check above already ran against it.
    write_profile(new, data)
    print(f"\nAPPLIED — {new} now holds {len(moves)} node(s), and no object moved. "
          f"Verify with `studio rewrite check`.")
