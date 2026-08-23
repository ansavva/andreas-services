"""`studio config sync` — put the repo's pose plates in the library, as nodes.

    studio config sync              # what is missing (dry run)
    studio config sync --apply

**This exists because a plate that is not a node is invisible.** `check_plates`
resolves each plate as a name path before a shoot spends anything, and a name
path is resolved against the catalog. So a plate sitting in the bucket with no
row is a plate the shoot cannot see — and the refusal it produces names
`dev-setup.sh`, which is exactly the script a person has already run.

That was the state this command was written to end. The plates were shared
material with **no catalog record by design**: nothing owned them, so nothing
recorded them, and `dev-shared-material.sh` pushed them straight into the bucket
with `aws s3 sync`. The entity model closed the exception that made that
readable — `GET /api/asset?key=` is gone, and there is one addressing scheme —
without closing the hole it left behind, which is that nothing gave the plates
the rows the new scheme requires.

WHY A `studio` COMMAND AND NOT A SHELL SYNC
-------------------------------------------
`aws s3 sync` writes objects. Nothing it can do writes a catalog row, so the
choice was between teaching a shell script the item shapes — a second place that
knows `NODE#`/`NAME#`, drifting from `services/catalog.py` the first time either
changed — and doing it through the API like every other write in this package.

The API needs a token, which is the real cost: `dev-setup.sh` runs from the
SessionStart hook and has never needed one. So this is best-effort there and
says what it skipped rather than failing a session.

**The source of truth is the repo**, `studio/config/`. The library holds a copy
because a model may only be handed a presigned URL of a stored object, never
bytes from disk. Editing a plate in the library rather than in the repo is how
the two diverge.

WHAT IT DOES NOT DO
-------------------
No delete, ever. A plate removed from the repo stays in the library, for the
reason `dev-shared-material.sh` gave when it refused `--delete`: whatever else
lives under `config/` was put there by something this command knows nothing
about.

It also does not re-upload a plate whose node already exists. Same-size is not
the test — existence is. A plate is a fixed asset; if one genuinely changes,
delete its node and re-run, which is rare enough to be worth being explicit
about.
"""
from __future__ import annotations

import mimetypes
import os
import pathlib

import click

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import auth, store
from studio_pipeline.domain import paths as P

#: What counts as a plate. Anything else under `studio/config/` is left alone —
#: a README, a licence, whatever a later addition puts there.
PLATE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def local_plates() -> list[tuple[str, str]]:
    """(name path in the library, absolute local path) for every plate in the repo.

    Ordered, so a dry run and the apply that follows list the same thing in the
    same order and can be read against each other.
    """
    root = os.path.join(str(STUDIO_DIR), P.CONFIG)
    found: list[tuple[str, str]] = []
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in PLATE_EXTS:
                continue
            local = os.path.join(dirpath, name)
            rel = os.path.relpath(local, root).replace(os.sep, "/")
            found.append((P.join(P.CONFIG, rel), local))
    return sorted(found)


def missing(plates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The plates with no node. One `resolve` each — there is no batch for it."""
    return [(path, local) for path, local in plates if not store.exists(path)]


@click.group("config", help=__doc__)
def main() -> None:
    pass


@main.command("sync")
@click.option("--apply", "apply_", is_flag=True,
              help="Actually upload. Without it this only reports what is missing.")
@click.option("--quiet", is_flag=True, help="Say nothing when there is nothing to do.")
def cmd_sync(apply_: bool, quiet: bool) -> int:
    """Upload every repo pose plate that has no node yet."""
    plates = local_plates()
    if not plates:
        click.echo(f"no plates under {STUDIO_DIR / P.CONFIG}", err=True)
        return 0

    try:
        absent = missing(plates)
    except auth.AuthError as exc:
        # Not a failure worth stopping a session for: `dev-setup.sh` sources
        # this on every start and a person may simply not be signed in yet.
        click.echo(f"config sync skipped — {exc}", err=True)
        return 0

    if not absent:
        if not quiet:
            click.echo(f"{len(plates)} plate(s) already in the library.", err=True)
        return 0

    if not apply_:
        click.echo(f"{len(absent)} plate(s) missing from the library:", err=True)
        for path, _local in absent:
            click.echo(f"  {path}", err=True)
        click.echo("Re-run with --apply to upload them.", err=True)
        return 0

    for path, local in absent:
        parent, _, _name = path.rpartition("/")
        store.folder(parent)
        node = store.upload(
            path, pathlib.Path(local),
            content_type=mimetypes.guess_type(local)[0] or "application/octet-stream",
        )
        click.echo(f"  {path}  {node['id']}")
    click.echo(f"uploaded {len(absent)} plate(s).", err=True)
    return 0
