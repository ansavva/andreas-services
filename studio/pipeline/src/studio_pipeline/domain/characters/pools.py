"""corpus/, seed/ and archive/ — material, not identity.

The fourth pool, `reference/`, is not here: what makes an image a reference is a
`REF#` row, and `refs.py` owns those. These three are ordinary folders holding
ordinary files, and that is the whole of what they are.

**They stopped being addressed by name path.** `pool_folder` returned
`characters/<slug>/corpus` and every command here composed keys under it, so a
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
    resolve,
    upload_file,
)

#: The three this module owns. `reference` is deliberately absent — adding to it
#: is a decision about identity and goes through `add-refs` (hard rule #2b).
MATERIAL_POOLS = ["archive", "corpus", "seed"]
#: `add-to` still refuses `reference`: putting a file there is not what makes it
#: identity, and `character add-refs` is the command that does (hard rule #2b).
#: LISTING one is a different act and is allowed — see `cmd_pool`.
LISTABLE_POOLS = ["archive", "corpus", "reference", "seed"]


@click.command("add-to")
@click.argument("name", required=True)
@click.argument("pool", required=True, type=click.Choice(MATERIAL_POOLS))
@click.argument("files", nargs=-1, required=True)
def cmd_add_to_pool(name, pool, files):
    """Add file(s) to corpus/, seed/ or archive/ — basenames kept as they are.

    Nothing here attaches a `REF#` row, which is the point of these pools being
    separate: material about a character is not a statement about who they are.
    Promoting one of these into identity is `studio character add-refs`.
    """
    record = resolve(name)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")
    folder = pool_folder(record, pool)
    for local in files:
        node = upload_file(folder["id"], local)
        print(f"  {node['id']}  {node['name']}", file=sys.stderr)
    print(f"added {len(files)} file(s) to {record['slug']}/{pool}/", file=sys.stderr)


@click.command("pool")
@click.argument("name", required=True)
@click.argument("pool", required=True, type=click.Choice(LISTABLE_POOLS))
@click.option("--group", default=None,
              help="A subfolder of the pool (e.g. seed/current, reference/face).")
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
@click.option("--unreferenced", is_flag=True,
              help="Only files no REF# row names — what is sitting in a folder without being identity.")
def cmd_pool(name, pool, group, json_, presign, unreferenced):
    """List what is actually IN a pool folder, which is not the same as the index.

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
        print(f"({record['slug']} has {which} in {where})", file=sys.stderr)
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
