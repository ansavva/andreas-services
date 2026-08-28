"""`studio character` — manage on-model characters in the media library.

A character is a **row with a UUID**, not a folder with a document in it. That
one sentence is the whole of what changed, and the docstring this replaces is
worth quoting because every line of it is now false:

    characters/<name>/profile.yaml   the bible (SOURCE OF TRUTH), including the
                                     DESCRIBED index of the reference library

The bible is a validated `profile` map on the record; the described index is one
`REF#` row per image; and `characters/<slug>/…` is not an address at all — a
bucket listing carried every character's name, production ones included, which
was hard rule #1 broken in the one place nobody looked.

    the record   id, slug, display_name, rev, root, hero,
                 default_set, profile          — one row, queryable
    the rows     one REF# per reference: group, order, description, tags,
                 naming a NODE ID
    the tree     a folder node the record names as `root`, starting with
                 reference/  corpus/  seed/  archive/

**The four folders are a starting layout, not a schema.** The record holds one
node id and no map of blessed folder names, so a person may rename `reference/`,
delete `archive/` or add their own — and nothing breaks, because an image is a
reference when a row says so rather than because of where it sits.

WHAT A SLUG IS NOW
------------------
A mutable label, unique in the library, that a person types. It is not the
primary key and it is not in any S3 key. So `character rename` is ONE `PATCH`:
no object is copied, no record is rewritten, and every reference, run binding
and `default_set` entry survives untouched because all three name node ids.
`rename.py` — a per-basename sweep across four pools plus a rewrite pass over
every run document — is deleted, and `domain/rewrite.py` with it.

THE REFERENCE LIBRARY IS INDEXED, NOT SENT WHOLE
------------------------------------------------
The engines cap reference images hard (Kling 7, Seedance 9, Nano Banana 14) and
send them in full, while a character holds far more. So each reference carries a
description and tags, `default_set` names the handful sent when nobody picks, and
selection is by node (`--pick`), by tag (`--tag`), or by that default. An
over-cap selection is REFUSED rather than truncated — by the API, so the CLI and
the web app cannot disagree about which images a generation saw.

Slot N is position N in the RESOLVED SELECTION. It never was a file number and
now it cannot be mistaken for one, because filenames carry nothing.

Requires a studio login (`studio login`). Not an AWS one — the CLI holds no
cloud credentials and knows no bucket name.

Subcommands:
  list                          Every character, with reference and file counts.
  show   <name>                 The record: id, rev, counts, the folders it has.
  create <name> [--from-profile FILE] [--display-name …]
                                The record, its slug claim, its root and four
                                pool folders, in one transaction.
  edit   <name>                 Round-trip the bible through
                                local/characters/<name>.yaml.
  set-profile <name> [FILE]     Replace the bible (FILE omitted: the local copy).
  rename <old> <new>            One PATCH. Nothing moves.
  textblock <name>              A pasteable identity paragraph.
  add-refs <name> [FILES…] [--from-run RUNREF] --to GROUP
                                Attach image(s) as references (hard rule #2b).
  refs   <name> [--group G]     The described index.
  selection <name> [--pick|--tag|--limit|--slots|--presign]
                                What a model would actually be shown.
  set-ref-desc / describe-refs  Describe one reference, or a batch atomically.
  order  <name> --group G NODE… Order references explicitly.
  regroup <name> NODE… --to G   Move references between groups. No object moves.
  detach <name> NODE…           Stop treating image(s) as identity.
  default-set <name> NODE…      What gets sent when nobody picks.
  add-to <name> POOL FILES…     Add to corpus/, seed/ or archive/.
  pool   <name> POOL            List one of those.
  turnaround <name> --project <p>  The standard reference set (wired in cli.py).

Examples:
  studio character create <name> --from-profile /tmp/<name>.yaml
  studio character add-refs <name> --to face --from-run <project>/latest#1
  studio character refs <name>
  studio character selection <name> --tag face --limit 7 --presign
  studio character rename <name> <new-name>
"""
from __future__ import annotations

import click

from studio_pipeline.domain.characters import pools, profile, refs


@click.group(help=__doc__)
def main():
    pass


# Registered here rather than declared with `@main.command` in each module.
# The group has to exist before a decorator can attach to it, so a module that
# decorated would have to import this one — and this one imports all of them.
# Assembling the tree in one place is what keeps the package acyclic, and it is
# also the only list of the whole command surface.
#
# `rename` moved into `profile.py` when `rename.py` was deleted: a rename is a
# field on the record, so it belongs beside the other record commands. `regroup`
# moved IN from `curate`, for the opposite reason — it writes no object, so it
# was never a curation of anything on disk.
for _command in (
    profile.cmd_list,
    profile.cmd_show,
    profile.cmd_create,
    profile.cmd_edit,
    profile.cmd_set_profile,
    profile.cmd_delete,
    profile.cmd_rename,
    profile.cmd_textblock,
    refs.cmd_refs,
    refs.cmd_selection,
    refs.cmd_add_refs,
    refs.cmd_set_ref_desc,
    refs.cmd_describe_refs,
    refs.cmd_order,
    refs.cmd_regroup,
    refs.cmd_detach,
    refs.cmd_default_set,
    pools.cmd_add_to_pool,
    pools.cmd_pool,
):
    main.add_command(_command)
