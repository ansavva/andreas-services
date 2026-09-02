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


from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import api, entities, store
from studio_pipeline.domain import TEMPLATES_DIR
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die

# `TEMPLATES_DIR`, not `__file__` arithmetic. This module used to be
# `domain/characters.py`, one level up, so `dirname(__file__) + "templates"`
# happened to be right; as a package it is one segment too deep. The same
# expression in `engine/turnaround.py` broke for exactly that reason. See
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


def resolve(character: str) -> dict:
    """An id, or a name matched client-side -> the character record.

    **An id is one call; a name is two**, and that is the cost of dropping
    slugs. A slug was library-unique, so `GET /api/characters/slug:<slug>`
    resolved one server-side against a claim row. A name is a free-text label:
    it identifies nothing, two characters may share one, and the API will not
    resolve it — so this lists and matches, and refuses an ambiguous name with
    the ids rather than picking one.

    Raises `api.NotFound` rather than dying, because every caller has a better
    message than this one does: `character list` for a person, `RefError` for
    the engine.
    """
    if character and character.startswith("char-"):
        return entities.get_character(character)
    try:
        found = P.by_name(entities.list_characters(), character, "character")
    except P.PathError as exc:
        raise api.NotFound(str(exc), 404) from exc
    return entities.get_character(found["id"])


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


def pool_tree_nodes(record: dict, pool: str) -> list[dict]:
    """Every file node in a pool INCLUDING its subfolders, each carrying a `path`.

    `pool_nodes` reads one folder, and `--group` reaches exactly one named
    subfolder of it. Both are the right shape for `curate`, which works a folder
    at a time on purpose. They are the wrong shape for a caller asking "what
    material does this character have", because a pool is a tree: `seed/` grows
    an `original/`, a `restored/` and a folder per age as soon as anyone tidies
    it, and a listing of the root then answers with whatever was never filed.

    That silence is what this exists to end. A turnaround resolved seed identity
    through the root listing alone, so a folder of restored photographs one
    level down was invisible to it — not refused, not mentioned, simply absent
    from the pool it believed it had read, while `--seed-pick` rejected every one
    of their names as "not in seed/". A pool bigger than an angle sends is a
    question for a person (`_too_many` asks it); a pool bigger than the code can
    see is not a question at all.

    The `path` on each entry is relative to the pool — `restored/<file>` one
    folder down, the bare basename at the root — so a name is unambiguous even
    when two folders hold the same one.
    """
    return store.walk_files_of(pool_folder(record, pool)["id"])


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


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


__all__ = [
    "IMG_EXTS", "LOCAL_DIR", "NAME_RE", "POOLS", "TEMPLATE", "die",
    "pool_folder", "pool_nodes", "read_text", "resolve", "upload_file",
    "write_text",
]
