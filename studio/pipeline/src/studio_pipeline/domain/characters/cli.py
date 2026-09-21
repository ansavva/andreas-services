"""`studio character` — manage on-model characters in the media library.

A character is a **row with a UUID**, not a folder with a document in it:

    the record   id, name, rev, root, hero, profile   — one row, queryable
    the tree     a folder node the record names as `root`, empty until
                 something is filed into reference/  corpus/  seed/  archive/

**Those four names are a convention, not a schema, and not even a starting
layout.** A character is created holding nothing, and a pool appears the first
time something is filed into it. An image is identity because it carries the
`default` tag, wherever it sits — see `refs.py`.

The commands are `domain/subjects.py`'s, bound to the character subject; a
location gets the same twelve under `studio location`. Requires a studio login
(`studio login`). Not an AWS one — the CLI holds no cloud credentials and
knows no bucket name.

Subcommands:
  list                          Every character, with sent and file counts.
  show   <name>                 The record: id, rev, counts, the folders it has.
  create <name> [--from-profile FILE]
                                The record, its index row and its root, in one
                                transaction.
  edit   <name>                 Round-trip the bible through
                                local/characters/<name>.yaml.
  set-profile <name> [FILE]     Replace the bible (FILE omitted: the local copy).
  rename <old> <new>            One PATCH. Nothing moves.
  delete <name>                 Remove the record; keeps the folder by default.
  textblock <name>              A pasteable identity paragraph.
  images <name> [--tag T]       Every image under it, and how each is tagged.
  selection <name> [--pick|--tag|--limit|--slots|--presign]
                                What a model would actually be shown.
  add-to <name> POOL FILES…     Add to a pool — any folder but reference/.
  pool   <name> POOL            List one the character has.

Examples:
  studio character create <name> --from-profile /tmp/<name>.yaml
  studio character images <name>
  studio character selection <name> --tag face --limit 7 --presign
  studio character rename <name> <new-name>
"""
from __future__ import annotations

import click

from studio_pipeline.domain.characters import pools, profile, refs


@click.group(help=__doc__)
def main():
    pass


# Assembled here rather than declared with `@main.command` in each module, so
# this is the one list of the whole command surface. Each module exports its
# share of the commands `subjects.commands` built for the character subject.
for _command in (
    profile.cmd_list,
    profile.cmd_show,
    profile.cmd_create,
    profile.cmd_edit,
    profile.cmd_set_profile,
    profile.cmd_delete,
    profile.cmd_rename,
    profile.cmd_textblock,
    refs.cmd_images,
    refs.cmd_selection,
    pools.cmd_add_to_pool,
    pools.cmd_pool,
):
    main.add_command(_command)
