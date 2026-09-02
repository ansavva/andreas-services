"""The character record — a row with a UUID, and the `studio character` tree.

One 1,235-line module until #305, then five, and now four: `base` (the record,
its pools, its node helpers), `profile` (the bible and its local round trip),
`refs` (what a model gets shown, which is tags) and `pools` (corpus/seed/
archive). `cli` assembles the command group.

**`rename.py` is gone.** It listed four pools, `PATCH`ed every basename carrying
the slug, rewrote the bible's index to match, and then swept every run document
in every project rewriting the paths they had recorded. A rename is one
`PATCH /api/characters/<id>` now, and the module has nothing left to do.

**This file re-exports what the rest of the pipeline imports**, so
`CHARACTER.load_profile` and its neighbours keep working from `engine/` and
`domain/curate.py`. Two names are new and are the seam those modules are written
against: `resolve(slug_or_id)` returns the record — the thing every command
starts from — and `selection_nodes` returns the entries a model would be shown,
resolved by the API rather than here.
"""

from studio_pipeline.domain.characters.base import (
    IMG_EXTS,
    LOCAL_DIR,
    NAME_RE,
    POOLS,
    TEMPLATE,
    check_name,
    die,
    pool_folder,
    pool_nodes,
    pool_tree_nodes,
    read_text,
    resolve,
    upload_file,
    write_text,
)
from studio_pipeline.domain.characters.cli import main
from studio_pipeline.domain.characters.profile import (
    PROFILE_KEYS,
    check_profile,
    do_pull,
    do_push,
    document,
    fetch_profile,
    load_profile,
    local_paths,
    parse_profile,
    remote_rev,
    save_profile,
    split_document,
    unified,
)
from studio_pipeline.domain.characters.refs import (
    DEFAULT_TAG,
    REFERENCE_POOL,
    selection_nodes,
)

__all__ = [
    "DEFAULT_TAG", "IMG_EXTS", "LOCAL_DIR", "NAME_RE", "POOLS", "PROFILE_KEYS",
    "REFERENCE_POOL", "TEMPLATE", "check_name", "check_profile", "die", "do_pull",
    "do_push", "document", "fetch_profile", "load_profile", "local_paths", "main",
    "parse_profile", "pool_folder", "pool_nodes", "pool_tree_nodes", "read_text",
    "remote_rev", "resolve", "save_profile", "selection_nodes", "split_document",
    "unified", "upload_file", "write_text",
]
