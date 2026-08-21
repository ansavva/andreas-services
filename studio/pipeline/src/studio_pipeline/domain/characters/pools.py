"""corpus/, seed/ and archive/ — material, not identity.

The fourth pool, `reference/`, is not here: it is indexed, cited by slot and
maintained by `refs.py`. These three keep whatever basenames they arrived with,
because renaming a source photo throws away what its filename recorded.
"""
from __future__ import annotations

import json
import os
import sys

import click

from studio_pipeline.adapters import store
from studio_pipeline.domain.characters.base import (
    check_name,
    die,
    pool_folder,
    put_file,
)

@click.command("add-to")
@click.argument("files", nargs=-1, required=True)
@click.argument("name", required=True)
@click.argument("pool", required=True, type=click.Choice(["archive", "corpus", "seed"]))
def cmd_add_to_pool(files, name, pool):
    """Add file(s) to corpus/, seed/ or archive/ — basenames kept as they are.

    Only reference/ is numbered, because only reference/ is cited by slot.
    Renaming a source photo throws away whatever its filename recorded.
    """
    check_name(name)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")
    folder = pool_folder(name, pool)
    store.folder(folder)
    for f in files:
        put_file(f, f"{folder}/{os.path.basename(f)}")
    print(f"added {len(files)} file(s) to {folder}/", file=sys.stderr)


@click.command("pool")
@click.argument("name", required=True)
@click.argument("pool", required=True, type=click.Choice(["archive", "corpus", "seed"]))
@click.option("--expires", type=int, default=3600)
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
def cmd_pool(name, pool, expires, json_, presign):
    """List a non-reference pool. These are material, not identity."""
    check_name(name)
    _warn_ignored_expiry(expires)
    folder = pool_folder(name, pool)
    keys = [f"{folder}/{e['name']}" for e in store.files(folder)]
    if not keys:
        print(f"({name} has nothing in {pool}/)", file=sys.stderr)
        return
    if presign:
        urls = [store.presign(k) for k in keys]
        print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
    elif json_:
        print(json.dumps(keys, indent=2))
    else:
        print("\n".join(keys))
    if pool == "archive":
        print("note: archive/ is retired material — do not feed it to a model unless "
              "the user asked for these specifically.", file=sys.stderr)



def _warn_ignored_expiry(expires: int) -> None:
    """`--expires` is accepted and ignored, loudly. See `objects/presign.py`."""
    context = click.get_current_context(silent=True)
    if context is None:
        return
    source = context.get_parameter_source("expires")
    if source is not None and source.name != "DEFAULT":
        click.echo(
            f"warning: --expires {expires} is ignored; the API sets the URL's lifetime.",
            err=True,
        )
