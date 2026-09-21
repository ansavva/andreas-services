"""What every part of the character record needs: the SUBJECT, and its pools.

A character is one of the two subjects `domain/subjects.py` knows how to
manage — the other is a location — and this module is where the character
half is declared: which API segment, which id prefix, which yaml template,
which keys that template has. Every function `curate`, `contact_sheet` and
`engine/refs.py` import from here is the generic one bound to `SUBJECT`.

**The four pools are a convention, not a schema — and not even something
`POST /api/characters` creates any more.** `POOLS` is what the CLI prints back
as a suggestion; a character is created holding none of them, and a pool
appears the first time something is filed into it. Nothing afterwards requires
any of them to exist, and an image is a reference because a tag on it says so
rather than because of where it sits.

Nothing here reaches AWS. `entities` and `store` are both HTTP.
"""
from __future__ import annotations

from studio_pipeline import STUDIO_DIR
from studio_pipeline.domain import TEMPLATES_DIR
from studio_pipeline.domain import paths as P
from studio_pipeline.domain import subjects as S
from studio_pipeline.domain.subjects import (
    IMG_EXTS,
    pool_folder,
    pool_names,
    pool_nodes,
    pool_tree_nodes,
    read_text,
    require_pool,
    upload_file,
    write_text,
)
from studio_pipeline.errors import die

# `TEMPLATES_DIR`, not `__file__` arithmetic: counting path segments is right
# for one file's depth only, and breaks the first time a module moves.
TEMPLATE = str(TEMPLATES_DIR / "profile.yaml")
# Working copies for `edit` live in the repo (git-ignored) so they are easy to
# open in an editor: <repo>/local/characters/<name>.yaml
LOCAL_DIR = str(STUDIO_DIR / "local" / "characters")
NAME_RE = P.NAME_RE

# A character starts with none of these; they are FOUR CONVENTIONAL NAMES, made
# on first use, and what distinguishes them is what they are FOR:
#
#   reference/  imagery that says who the character IS — conventionally, since
#               the `default` tag is what makes an image identity wherever it sits.
#   corpus/     collected images and video of or for the character — uploads,
#               keeper clips. Material, not identity.
#   seed/       the founding real-world source photos. Small, historical,
#               never sent to a model by default.
#   archive/    retired material. NEVER referenced unless the user asks for it
#               by name — that is the whole point of it having a name.
POOLS = P.CHAR_POOLS

# The keys of the DOCUMENT a person edits — the bible as one map, which is the
# shape `load_profile` returns and the shape `edit` round-trips. It is the
# record's `profile` plus the promoted `name`.
PROFILE_KEYS = (
    "name",
    "identity",
    "face",
    "body",
    "wardrobe",
    "voice",
    "rendering",
    "consistency",
    "text_identity_block",
)

SUBJECT = S.Subject(
    kind="character",
    segment="characters",
    id_prefix="char-",
    cli="character",
    template=TEMPLATE,
    local_dir=LOCAL_DIR,
    profile_keys=PROFILE_KEYS,
    group_example="face",
    pools=POOLS,
    next_step="seed photos with `studio character add-to {name} seed <img>...`",
)


#: The twelve `studio character` commands, built ONCE. `profile`, `refs` and
#: `pools` each export their share under the names `cli.py` assembles.
COMMANDS = S.commands(SUBJECT)


def resolve(character: str) -> dict:
    """An id, or a name matched client-side -> the character record."""
    return S.resolve(SUBJECT, character)


__all__ = [
    "COMMANDS", "IMG_EXTS", "LOCAL_DIR", "NAME_RE", "POOLS", "PROFILE_KEYS", "SUBJECT", "TEMPLATE",
    "die", "pool_folder", "pool_names", "pool_nodes", "pool_tree_nodes", "read_text",
    "require_pool", "resolve", "upload_file", "write_text",
]
