"""A character's pools — material, not identity.

A pool is any folder under the character's root. `corpus/`, `seed/` and
`archive/` are the conventional starting names, and nothing here knows them:
a character whose only pool is `original/` is as valid as one with all four,
and a pool a person made in the app is listable and addable the moment it
exists. `reference/` is the one name this module treats specially, and only on
the way IN: what makes an image identity is a tag, and `refs.py` owns that.
The pools are ordinary folders holding ordinary files, and that is the whole of
what they are.

**They stopped being addressed by name path.** `pool_folder` returned
`characters/<name>/corpus` and every command here composed keys under it, so a
rename moved four folders' worth of objects. It returns a **node** now, resolved
under the record's `root` and created if it is not there — so these commands
work on a character whose `archive/` somebody deleted, and keep working on one
whose folders were renamed.

Basenames are kept, as they always were. Renaming a source photo throws away
whatever its filename recorded, and there is no numbering left anywhere to
rewrite it into.
"""
from __future__ import annotations

import json
import os
import sys

import click

from studio_pipeline.adapters import entities, store
from studio_pipeline.domain.characters.base import (
    die,
    pool_folder,
    pool_nodes,
    require_pool,
    resolve,
    upload_file,
)

#: The one pool `add-to` refuses. Putting a file there is not what makes it
#: identity — the `default` tag is — and `character add-refs` is the command
#: that decides that (hard rule #2b). LISTING it is a different act and is
#: allowed — see `cmd_pool`. Every other folder name is a pool: the four the
#: docs name were a `click.Choice` here until a character turned up whose only
#: pool was `original/`, and `add-to` and `pool` both refused it.
IDENTITY_POOL = "reference"


@click.command("add-to")
@click.argument("name", required=True)
@click.argument("pool", required=True)
@click.argument("files", nargs=-1, required=True)
def cmd_add_to_pool(name, pool, files):
    """Add file(s) to a pool — any folder name; basenames kept as they are.

    The pool is created under the character's root if it is not there. Nothing
    here tags an image, which is the point of the pools being separate:
    material about a character is not a statement about who they are.
    Promoting one of these into identity is `studio character add-refs`, and
    `reference/` is refused here for exactly that reason (hard rule #2b).
    """
    if pool.strip("/") == IDENTITY_POOL:
        die(f"refusing to add to {IDENTITY_POOL}/: a file there is not identity, a tag is. "
            "Use `studio character add-refs` (hard rule #2b).")
    record = resolve(name)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")
    folder = pool_folder(record, pool)
    for local in files:
        node = upload_file(folder["id"], local)
        print(f"  {node['id']}  {node['name']}", file=sys.stderr)
    print(f"added {len(files)} file(s) to {record['name']}/{pool}/", file=sys.stderr)


@click.command("pool")
@click.argument("name", required=True)
@click.argument("pool", required=True)
@click.option("--group", default=None,
              help="A subfolder of the pool (e.g. seed/current, reference/face).")
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
@click.option("--unreferenced", is_flag=True,
              help="Only files no REF# row names — what is sitting in a folder without being identity.")
def cmd_pool(name, pool, group, json_, presign, unreferenced):
    """List what is actually IN a pool folder, which is not the same as the index.

    POOL is any folder name under the character's root — `studio character
    show <name>` prints the ones it has.

    Node ids and names, where this printed S3 keys. A key was never something a
    caller could do anything with — it could not be fetched without credentials
    the CLI does not have — and an id is what every other command here takes.

    **`reference` is listable now.** It used to be excluded on the grounds that
    the pools are material and references are identity — which is true of the
    ROWS and not of the folder. A file can sit in `reference/body/` with no
    `REF#` row naming it, and nothing then listed it: `character refs` reads the
    index and this command refused the pool. Twelve such files went unnoticed in
    one library because the only two views of `reference/` both looked at the
    index. `--unreferenced` is the question that finds them.

    `--group` reaches one level down, because a pool is a tree now — `seed/`
    with an `original/` and a folder per age, `reference/` with one per group.
    """
    record = resolve(name)
    require_pool(record, pool)  # a listing makes nothing; a typo is a refusal
    entries = pool_nodes(record, pool, group)
    if unreferenced:
        # **Files nothing sends.** A set difference on node ids rather than a
        # filename comparison, which is what makes it reliable; what changed is
        # where the answer comes from — the `default` tag on each image, rather
        # than a `REF#` row pointing at it.
        named = {entry["id"] for entry in
                 entities.character_images(record["id"], tags=["default"])}
        entries = [e for e in entries if e["id"] not in named]
    where = f"{pool}/{group}" if group else f"{pool}/"
    if not entries:
        which = "unreferenced files" if unreferenced else "nothing"
        print(f"({record['name']} has {which} in {where})", file=sys.stderr)
        return
    if presign:
        urls = [store.presign_node(entry["id"]) for entry in entries]
        print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
    elif json_:
        print(json.dumps(entries, indent=2))
    else:
        for entry in entries:
            print(f"{entry['id']}  {entry['name']}")
    if pool == "archive":
        print("note: archive/ is retired material — do not feed it to a model unless "
              "the user asked for these specifically.", file=sys.stderr)
