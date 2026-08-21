"""The character record — `characters/<name>/` and the `studio character` tree.

One 1,235-line module until #305. It is now five: `base` (names, pools, paths),
`profile` (the bible and its local round trip), `refs` (the described reference
index), `pools` (corpus/seed/archive) and `rename`. `cli` assembles the command
group.

**This file re-exports what the rest of the package already imports**, so
`CHARACTER.load_profile` and the nine other names `engine/` and `curate` reach
for keep working. That is deliberate and not permanent scaffolding: the split
was made reviewable by keeping every call site outside this package unchanged,
and moving those imports onto the submodule that owns each name is a separate,
mechanical pass.
"""

from studio_pipeline.domain.characters.base import (
    IMG_EXTS,
    LOCAL_DIR,
    NAME_RE,
    POOLS,
    PROFILE_CT,
    PROFILE_FILE,
    TEMPLATE,
    check_name,
    die,
    group_prefix,
    pool_folder,
    pool_max_index,
    profile_key,
    put_file,
    read_text,
    write_text,
)
from studio_pipeline.domain.characters.cli import main
from studio_pipeline.domain.characters.profile import (
    check_profile,
    do_pull,
    do_push,
    fetch_profile,
    load_profile,
    local_paths,
    parse_profile,
    remote_etag,
    unified,
    write_profile,
)
from studio_pipeline.domain.characters.refs import (
    read_index,
    ref_files,
    ref_root,
    resolve_selection,
    sync_index,
)
from studio_pipeline.domain.characters.rename import (
    default_display_name,
    rename_in_profile,
    rename_moves,
    renamed_file,
)

__all__ = [
    "IMG_EXTS", "LOCAL_DIR", "NAME_RE", "POOLS", "PROFILE_CT", "PROFILE_FILE",
    "TEMPLATE", "check_name", "check_profile", "default_display_name", "die",
    "do_pull", "do_push", "fetch_profile", "group_prefix", "load_profile",
    "local_paths", "main", "parse_profile", "pool_folder", "pool_max_index",
    "profile_key", "put_file", "read_index", "read_text", "ref_files", "ref_root",
    "remote_etag", "rename_in_profile", "rename_moves", "renamed_file",
    "resolve_selection", "sync_index", "unified", "write_profile", "write_text",
]
