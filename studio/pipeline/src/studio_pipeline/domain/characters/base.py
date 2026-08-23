"""What every part of the character record needs: the record, and its pools.

**Nothing here builds a key any more, and that is the whole of the change.**
This module used to hold `pool_folder(name, pool)` returning
`characters/<name>/reference`, `group_prefix` returning `<name>_face_`, and
`pool_max_index` scanning those basenames for the highest trailing number — a
naming scheme that made the slug a primary key, the folder a schema, and the
filename an ordering. All three are gone:

===========================  =============================================
`profile_key(name)`          the bible is a field on the record, not an
                             object in the bucket (`profile.py`)
`group_prefix(name, group)`  a reference's group is an attribute of its
                             `REF#` row, so a filename carries nothing
`pool_max_index(...)`        numbering existed to order references; order
                             is an attribute of the row, gapped by 1000
`pool_folder(name, pool)`    a name path; it is a **node** now, resolved
                             under the record's `root` and made if absent
===========================  =============================================

`put_file` went the same way and came back as `upload_file`: it took a name
path and now takes the id of the folder to write into, because every caller
already holds a node and none of them should be composing a string that the
next rename invalidates.

**The four pools are a convention, not a schema.** `POOLS` is what
`POST /api/characters` creates with a new character and what the CLI prints
back. Nothing afterwards requires any of them to exist: a person may rename
`reference/`, delete `archive/` or add their own folder, and an image is a
reference because a `REF#` row says so rather than because of where it sits.
`pool_folder` therefore *ensures* rather than *asserts* — the self-healing the
spec's layout section describes.

Nothing here reaches AWS. `entities` and `store` are both HTTP.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

import click

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import entities, store
from studio_pipeline.domain import TEMPLATES_DIR
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die

# `TEMPLATES_DIR`, not `__file__` arithmetic. This module used to be
# `domain/characters.py`, one level up, so `dirname(__file__) + "templates"`
# happened to be right; as a package it is one segment too deep. The same
# expression in `engine/shoot.py` broke for exactly that reason. See
# `STUDIO_DIR` in the root `CLAUDE.md`: counting path segments is right for one
# file's depth only.
TEMPLATE = str(TEMPLATES_DIR / "profile.yaml")
# Working copies for `edit` live in the repo (git-ignored) so they are easy to
# open in an editor: <repo>/local/characters/<slug>.yaml
LOCAL_DIR = str(STUDIO_DIR / "local" / "characters")
NAME_RE = P.NAME_RE

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}

# A character starts with FOUR folders, and what distinguishes them is what
# they are FOR:
#
#   reference/  imagery that says who the character IS. The `REF#` rows point
#               at files that conventionally live here, in purpose subfolders,
#               because a model takes only a handful at once (Kling 7,
#               Seedance 9, Nano Banana 14) and a character holds far more.
#   corpus/     collected images and video of or for the character — uploads,
#               keeper clips. Material, not identity.
#   seed/       the founding real-world source photos. Small, historical,
#               never sent to a model by default.
#   archive/    retired material. NEVER referenced unless the user asks for it
#               by name — that is the whole point of it having a name.
#
# It is a tuple of names rather than the `{pool: {"folder": pool}}` map it was:
# the map existed so a pool could one day have a different folder name from its
# own, and nothing ever wanted that. The project's `input/` pool
# (`projects.py`) is a separate thing entirely — working material for a piece
# of work, not anything about a character.
POOLS = P.CHAR_POOLS


def check_name(name: str) -> None:
    """Characters and projects share one slug rule.

    **It is a legibility rule now, not a filesystem one** — a slug is an
    attribute on a row and no longer a path segment. See `paths.check_slug`.
    """
    try:
        P.check_slug(name, "character name")
    except P.PathError as exc:
        die(str(exc))


def resolve(character: str) -> dict:
    """A slug or an id -> the character record. **One call.**

    Slug resolution is `GET /api/characters/slug:<slug>`: two reads server-side
    against a claim row, where it used to be a folder listing plus a fetch of a
    YAML document. The caller gets the whole record — id, `rev`, `root`,
    `default_set` and the bible — so nothing goes back for any of it.

    Raises `api.NotFound` rather than dying, because every caller has a better
    message than this one does: `character list` for a person, `RefError` for
    the engine.
    """
    if character and character.startswith("char-"):
        return entities.get_character(character)
    check_name(character)
    return entities.get_character(entities.address(character))


def pool_folder(record: dict, pool: str) -> dict:
    """The node of one pool folder, created if it is not there.

    **Ensuring, not asserting.** The pools are a starting layout; a route or a
    command that cannot find its conventional folder is entitled to make one
    and never to guess, because nothing structural hangs off the folder any
    more. Deleting `archive/` and then archiving something used to be an error
    about a missing prefix; it is now a folder appearing.
    """
    return store.ensure_child_folder(record["root"], pool)


def pool_nodes(record: dict, pool: str, group: str | None = None) -> list[dict]:
    """The file nodes in a pool, natural-sorted, optionally one level deeper.

    `group` reaches a subfolder of the pool — `reference/face/` — and exists for
    `curate`, which still works a folder at a time because deduplicating means
    reading bytes and reading a whole subtree's worth is what it is trying to
    avoid.

    The natural sort survives the entity model even though ordering does not
    depend on filenames any more: a person reading `character pool <slug> seed`
    still wants `_2` before `_10`, and `store.files_of` is where that lives.
    """
    folder = pool_folder(record, pool)
    if group:
        folder = store.ensure_child_folder(folder["id"], group)
    return store.files_of(folder["id"])


def upload_file(parent_id: str, local: str, name: str | None = None,
                content_type: str | None = None) -> dict:
    """Upload one local file INTO a folder node, and return the node it made.

    **Takes an id, where `put_file` took a name path.** The old signature made
    every caller compose `characters/<slug>/reference/<group>/<basename>`, which
    is three facts a rename can invalidate and one that a person chose; this
    takes the folder the caller already resolved and the basename the file
    already has.

    The basename is kept. Renaming an arriving file threw away the only thing
    its name recorded, and the numbering it used to be rewritten into is a row
    attribute now.
    """
    source = Path(local)
    filename = name or source.name
    ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return store.upload_into(parent_id, filename, source, content_type=ct)


def warn_ignored_expiry(expires: int) -> None:
    """`--expires` is accepted and ignored, loudly. See `objects/presign.py`.

    One copy for the whole package. The API signs every URL against its own
    credentials and owns the TTL, so a number typed on the command line cannot
    be honoured — and silently ignoring it is how somebody comes to believe a
    link lasts a day.
    """
    context = click.get_current_context(silent=True)
    if context is None:
        return
    source = context.get_parameter_source("expires")
    if source is not None and source.name != "DEFAULT":
        click.echo(
            f"warning: --expires {expires} is ignored; the API sets the URL's lifetime.",
            err=True,
        )


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


__all__ = [
    "IMG_EXTS", "LOCAL_DIR", "NAME_RE", "POOLS", "TEMPLATE", "check_name", "die",
    "pool_folder", "pool_nodes", "read_text", "resolve", "upload_file",
    "warn_ignored_expiry", "write_text",
]
