"""`studio character` — manage on-model characters stored in the
studio-prod-media-us-east-1 S3 bucket.

A character is DATA, not a skill: each one is an S3 record under
`characters/<name>/` (see the `studio-media-s3` skill), and this one tool manages them all:

    characters/<name>/profile.yaml   the bible (SOURCE OF TRUTH), including the
                                     DESCRIBED index of the reference library
    characters/<name>/reference/     generated character imagery, in purpose
                                     subfolders: face/ body/ wardrobe/ frame/ …
    characters/<name>/corpus/        collected material — uploads, keeper clips
    characters/<name>/seed/          the founding real-world source photos
    characters/<name>/archive/       retired material; never used unless named

A character holds no production history: runs, chains, scenes and movies live
under `projects/<project>/`, because one piece of work can involve several
characters. A run records which ones it used.

THE REFERENCE LIBRARY IS INDEXED, NOT SENT WHOLE
------------------------------------------------
The engines cap reference images hard (Kling 7, Seedance 9, Nano Banana 14) and
send them in full, while `reference/` holds far more than that. So the bible
carries `references:` — every image with a description and tags — plus
`default_set:`, the handful sent when nobody picks. Selection is by name
(`--pick`), by tag (`--pick-tag`), or by that default. An over-cap selection is
refused rather than truncated: which images a generation saw should not be
decided by whatever a folder listing returned.

Slot N is position N in the RESOLVED SELECTION — not a trailing file number.
With subfolders, filename numbers are only unique within a group.

The bible is STRUCTURED YAML on one schema (templates/profile.yaml): the same
keys for every character, so a prompt or a check reads `consistency.must` or
`identity.signature_features` by path instead of pattern-matching prose. It
describes WHO the character is — never how the record was assembled.

Requires an AWS login (`aws login`; see the `studio-media-s3` skill).

Subcommands:
  list                         Every character.
  show   <name>                Print the character's profile.yaml.
  create <name> [--from-profile FILE]
                               Create the record from a bible (or the blank
                               templates/profile.yaml).
  set-profile <name> FILE      Replace the bible.
  edit   <name>                Round-trip the bible for local editing: the first
                               run downloads it to local/characters/<name>.yaml,
                               a later run uploads your edits back. Refuses to
                               overwrite a bible that changed in S3 meanwhile.
  textblock <name>             A pasteable identity block, for engines driven
                               from a start frame with no reference set.
  add-refs <name> FILE... [--to GROUP]
                               Add reference image(s), numbered within a group.
  refs   <name> [--describe | --pick … | --pick-tag … | --presign | --keys]
                               Read the index, or resolve a selection of it.
  set-ref-desc / describe-refs / sync-refs / default-set
                               Maintain the index: describe one image, describe
                               a batch atomically, reconcile against the folder,
                               or name what gets sent by default.
  add-to <name> POOL FILE...   Add to corpus/, seed/ or archive/.
  pool   <name> POOL           List one of those.
  rename <old> <new>           Give a character a new slug — objects, bible and
                               the records that name them, together. DRY RUN
                               unless --apply.

Examples:
  studio character create <name> --from-profile /tmp/<name>.yaml
  studio character add-refs <name> --to face /tmp/*.png
  studio character refs <name> --describe
  studio character refs <name> --pick-tag face --presign --json
  studio character rename <name> <new-name> --apply
"""
from __future__ import annotations

import json
import sys

import click

from studio_pipeline.domain import paths as P
from studio_pipeline.domain.characters import pools, profile, refs, rename

@click.command("list")
@click.option("--json", "json_", is_flag=True)
def cmd_list(json_):
    # No S3 client: `character list` is the first command that needs no AWS at
    # all. The catalog answers it, and `main()` builds no client for a command
    # that does not ask for one.
    names = P.list_characters()
    if json_:
        print(json.dumps(names, indent=2))
    elif names:
        print("\n".join(names))
    else:
        print("(no characters yet — create one with `studio character create <name>`)", file=sys.stderr)



@click.group(help=__doc__)
def main():
    pass


# Registered here rather than declared with `@main.command` in each module.
# The group has to exist before a decorator can attach to it, so a module that
# decorated would have to import this one — and this one imports all of them.
# Assembling the tree in one place is what keeps the package acyclic, and it is
# also the only list of the whole command surface.
for _command in (
    cmd_list,
    profile.cmd_show,
    profile.cmd_textblock,
    profile.cmd_create,
    profile.cmd_set_profile,
    profile.cmd_edit,
    refs.cmd_add_refs,
    refs.cmd_sync_refs,
    refs.cmd_set_ref_desc,
    refs.cmd_describe_refs,
    refs.cmd_default_set,
    refs.cmd_refs,
    pools.cmd_add_to_pool,
    pools.cmd_pool,
    rename.cmd_rename,
):
    main.add_command(_command)
