"""What every part of the character record needs: names, pools, paths.

Split out of one 1,235-line module (#305). The four command modules beside this
one all import it and none imports another's commands, so the package has no
cycle to reason about — which the single file did have, in the form of `curate`
and `shoot` importing it back and being deferred to function scope for it.

Nothing here reaches storage on its own. `pool_max_index` and `put_file` still
take an S3 client because their call sites do; that goes with the API migration
and not with the move.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import store
from studio_pipeline.domain import TEMPLATES_DIR
from studio_pipeline.domain import paths as P
from studio_pipeline.errors import die

PROFILE_FILE = "profile.yaml"
PROFILE_CT = "application/yaml"
# `TEMPLATES_DIR`, not `__file__` arithmetic. This module used to be
# `domain/characters.py`, one level up, so `dirname(__file__) + "templates"`
# happened to be right; as a package it is one segment too deep. The same
# expression in `engine/shoot.py` — via `CHARACTER.__file__` — broke for exactly
# that reason and is fixed the same way. See `STUDIO_DIR` in the root
# `CLAUDE.md`: counting path segments is right for one file's depth only.
TEMPLATE = str(TEMPLATES_DIR / PROFILE_FILE)
# Working copies for `edit` live in the repo (git-ignored) so they are easy to
# open in an editor: <repo>/local/characters/<name>.yaml
LOCAL_DIR = str(STUDIO_DIR / "local" / "characters")
NAME_RE = P.NAME_RE




def check_name(name: str) -> None:
    """Characters and projects share one naming rule — both become path segments.

    There is no reserved-name list any more. Characters live under
    `characters/`, so a project called `misc` and a folder called `phrasebook`
    simply are not characters, rather than being characters that must be
    excluded by name.
    """
    try:
        P.check_slug(name, "character name")
    except P.PathError as exc:
        die(str(exc))


# A character has FOUR pools, and what distinguishes them is what they are FOR:
#
#   reference/  generated character imagery — body positions, face angles,
#               wardrobe. Organised in purpose subfolders and INDEXED in the
#               bible, because a model takes only a handful at once (Kling 7,
#               Seedance 9, Nano Banana 14) and the folder holds far more than
#               that. A subset is chosen deliberately; the folder is never the
#               answer by itself.
#   corpus/     collected images and videos of or for the character — uploads,
#               keeper clips. Material, not identity.
#   seed/       the founding real-world source photos the character was built
#               from. Small, historical, never sent to a model by default.
#   archive/    retired material. NEVER referenced unless the user asks for it
#               by name — that is the whole point of it having a name.
#
# The project's `input/` pool (projects.py) is a separate thing entirely: it is
# working material for a piece of work, not anything about a character.
POOLS = {p: {"folder": p} for p in P.CHAR_POOLS}


def pool_folder(name: str, pool: str) -> str:
    """Tree-relative prefix of a pool — the one place a pool path is built."""
    return P.char_pool_prefix(name, pool)


def group_prefix(name: str, group: str | None) -> str:
    """Basename prefix inside reference/: `<name>_<group>_` or `<name>_`."""
    return f"{name}_{group}_" if group else f"{name}_"


def pool_max_index(name: str, pool: str, group: str | None = None) -> int:
    """Highest N among numbered files in a pool (optionally one subfolder).

    **The subfolder exclusion is gone with the recursive listing that needed
    it.** `store.files` is one folder deep, so a file in `reference/face/` is
    simply not among `reference/`'s children — where `list_keys` returned the
    whole subtree and the filter had to put it back.

    Read off the names rather than counted, for the reason `projects.py` gives:
    a pool is pruned by hand, so `len()` would reuse an index and two images
    would end up answering to one name.
    """
    pat = re.compile(rf"^{re.escape(group_prefix(name, group))}(\d+)\.")
    folder = pool_folder(name, pool) + (f"/{group}" if group else "")
    hi = 0
    for entry in store.files(folder):
        if (m := pat.match(entry["name"])):
            hi = max(hi, int(m.group(1)))
    return hi


def put_file(local: str, path: str, content_type: str | None = None) -> str:
    """Upload one local file to a name path, creating its folder if needed.

    Returns the PATH, where this returned an `s3://bucket/key` URI. The CLI has
    no bucket name any more, and printing a guessed one would be worse than
    printing what was actually written — the call `objects/upload.py` already
    made.
    """
    import mimetypes

    ct = content_type or mimetypes.guess_type(local)[0] or "application/octet-stream"
    parent, _, _name = path.strip("/").rpartition("/")
    store.folder(parent)
    store.upload(path, Path(local), content_type=ct)
    return path




def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}


def profile_key(name: str) -> str:
    return P.profile_key(name)
