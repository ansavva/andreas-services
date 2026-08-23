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

from studio_pipeline.adapters import store
from studio_pipeline.domain.characters.base import (
    die,
    pool_folder,
    pool_nodes,
    resolve,
    upload_file,
    warn_ignored_expiry,
)

#: The three this module owns. `reference` is deliberately absent — adding to it
#: is a decision about identity and goes through `add-refs` (hard rule #2b).
MATERIAL_POOLS = ["archive", "corpus", "seed"]


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
@click.argument("pool", required=True, type=click.Choice(MATERIAL_POOLS))
@click.option("--expires", type=int, default=3600)
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
def cmd_pool(name, pool, expires, json_, presign):
    """List a non-reference pool. These are material, not identity.

    Node ids and names, where this printed S3 keys. A key was never something a
    caller could do anything with — it could not be fetched without credentials
    the CLI does not have — and an id is what every other command here takes.
    """
    record = resolve(name)
    warn_ignored_expiry(expires)
    entries = pool_nodes(record, pool)
    if not entries:
        print(f"({record['slug']} has nothing in {pool}/)", file=sys.stderr)
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
