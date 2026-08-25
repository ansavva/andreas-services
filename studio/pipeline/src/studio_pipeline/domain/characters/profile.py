"""The bible: its schema, the record field it lives in, and the local round trip.

THE BIBLE IS A FIELD ON A ROW, NOT A DOCUMENT IN A BUCKET
---------------------------------------------------------
`characters/<slug>/profile.yaml` is gone. The bible is `profile` on the
character record — a validated map the API owns — and three of its keys were
promoted out of it into real fields, because they are not description, they are
identity:

    name          -> the record's `slug`, library-unique and mutable
    display_name  -> a field, so a listing can draw a card without parsing YAML
    fictional     -> a field, because the consent question governs publication
                     and must be answerable without reading a document

Two more keys became rows rather than fields: `references:` is one `REF#` row
per image and `default_set:` is an ordered list of node ids on the record. So
nothing in the bible names a file any more, and a rename cannot strand a
description.

**`load_profile` merges the three promoted fields back in**, and that is a
compatibility seam with a reason rather than a courtesy: `engine/shoot.py` and
`domain/prompt.py` read a bible as one map and index it by key —
`profile["wardrobe"]`, `profile["consistency"]`, and `name` / `display_name`
where a prompt has to write the character into prose. Handing them a map with
three keys silently missing would not fail; it would render slightly worse
prompts, which is the failure that does not get noticed.

`rev` CLOSED THE WINDOW THAT `updated_at` LEFT OPEN
---------------------------------------------------
This module used to carry a long argument about conflict detection: it compared
the S3 ETag, then compared the node's `updated_at` when the catalog stopped
exposing an ETag, and admitted in its own docstring that both were
**check-then-write** — read the version, compare it here, then write, with a
window in between where somebody else's write lands and is lost. It closed with
"closing that window needs an `If-Match` on the API".

That is what `rev` is. `PATCH /api/characters/<id>/profile` takes `{profile, rev}`
and the API refuses a stale one with a `ConditionExpression`, so the comparison
happens where the write happens and there is no gap at all. A `409` arrives as
`api.Conflict` and means exactly one thing: somebody wrote since you read.

The local sidecar survives with a new job. It held the ETag, then `updated_at`;
it now holds the `rev` observed at pull time, and `edit --push` sends *that*
rather than whatever the record says today — so a push of a copy pulled an hour
ago is refused by the API rather than quietly reverting every description
written since.
"""
from __future__ import annotations

import difflib
import json
import os
import sys

import click
import yaml

from studio_pipeline.adapters import api, entities
from studio_pipeline.adapters import store
from studio_pipeline.domain.characters.base import (
    LOCAL_DIR,
    POOLS,
    TEMPLATE,
    check_name,
    die,
    read_text,
    resolve,
    write_text,
)

# The keys of the DOCUMENT a person edits — the bible as one map, which is the
# shape `load_profile` returns and the shape `edit` round-trips. It is the
# record's `profile` plus the three promoted fields; `references` and
# `default_set` are deliberately absent, because they are rows and a document
# that carried them would invite someone to edit a copy of them.
PROFILE_KEYS = (
    "schema_version",
    "name",
    "display_name",
    "fictional",
    "identity",
    "face",
    "body",
    "wardrobe",
    "voice",
    "rendering",
    "consistency",
    "text_identity_block",
)
#: The three that live on the record rather than inside `profile`.
PROMOTED = ("name", "display_name", "fictional")


def parse_profile(text: str, where: str) -> dict:
    """Parse a bible, or die with the YAML error and where it came from."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        die(f"{where} is not valid YAML:\n  {exc}")
    if not isinstance(data, dict):
        die(f"{where} must be a YAML mapping (got {type(data).__name__}).")
    return data


def check_profile(data: dict, where: str, name: str | None = None) -> None:
    """Refuse a bible that has drifted off the shared schema.

    `references:` and `default_set:` are now rows, so a bible carrying them is
    warned about rather than refused: an old document should still be editable
    into a new one, and the warning is what says the keys will be ignored.
    """
    missing = [k for k in PROFILE_KEYS if k not in data]
    if missing:
        die(
            f"{where} is missing required key(s): {', '.join(missing)}\n"
            "  every character carries the same schema — see templates/profile.yaml."
        )
    stale = [k for k in ("references", "default_set") if k in data]
    if stale:
        print(
            f"warning: {where} still carries {', '.join(stale)}; both are rows now and "
            "this copy is ignored. Use `studio character refs` / `default-set`.",
            file=sys.stderr,
        )
    extra = [k for k in data if k not in PROFILE_KEYS and k not in ("references", "default_set")]
    if extra:
        print(
            f"warning: {where} has key(s) outside the schema: {', '.join(extra)}",
            file=sys.stderr,
        )
    if name and data.get("name") != name:
        die(f"{where} declares name: {data.get('name')!r}, but this is character {name!r}.")


def document(record: dict) -> dict:
    """The record as the one map every reader of a bible expects.

    `name` is the slug, deliberately: the bible's `name:` key WAS the slug and
    every downstream reader spells it `name`. Rewriting them all to say `slug`
    would be a rename of a concept that did not change.
    """
    profile = dict(record.get("profile") or {})
    merged = {
        "schema_version": profile.pop("schema_version", None) or record.get("schema_version"),
        "name": record["slug"],
        "display_name": record.get("display_name") or record["slug"],
        "fictional": bool(record.get("fictional", True)),
    }
    merged.update(profile)
    return merged


def load_profile(name: str) -> dict:
    """The bible of one character, as one map. **The reader every engine uses.**

    Returns the record's `profile` with `name` (= the slug), `display_name` and
    `fictional` merged back in — see the module docstring for why those three
    are fields and why they are put back here. One API call; there is no
    document to fetch and no YAML to parse.
    """
    try:
        return document(resolve(name))
    except api.NotFound:
        die(f"no character {name!r} (see `studio character list`).")


def split_document(data: dict) -> tuple[dict, str, bool]:
    """A document -> (the `profile` map, display_name, fictional).

    The inverse of `document`. `name` is dropped rather than written: the slug
    is claimed by a row and a rename is `PATCH /api/characters/<id>`, so a
    bible that disagrees with the record cannot rename anything and must not
    look as though it could.
    """
    profile = {k: v for k, v in data.items()
               if k not in PROMOTED and k not in ("references", "default_set")}
    display = str(data.get("display_name") or "").strip()
    if display.startswith("<"):  # the unfilled template placeholder
        display = ""
    return profile, display, bool(data.get("fictional", True))


def save_profile(record: dict, data: dict, rev: int | None = None) -> dict:
    """Write a document back. **One compare-and-swap, not a check then a write.**

    `rev` is the revision the caller last saw — the sidecar's for `edit --push`,
    the record's own for an explicit file. The API refuses a stale one, which is
    the whole of the conflict story now; nothing here re-reads and compares.

    `display_name` and `fictional` ride on the record rather than in `profile`,
    so a document that changes one costs a second call. It is done second and
    with the bumped `rev`, so a failure leaves the bible written and the label
    stale — the recoverable half, and re-running fixes it.
    """
    char_id = record["id"]
    profile, display, fictional = split_document(data)
    try:
        after = entities.put_profile(char_id, profile,
                                     record["rev"] if rev is None else rev)
    except api.Conflict as exc:
        die(f"{exc}\n       {record['slug']}'s bible was written by someone else since "
            "you read it — re-run `edit` to pick it up rather than overwriting.")
    if (display and display != after.get("display_name")) or \
            fictional != bool(after.get("fictional", True)):
        after = entities.patch_character(char_id, after["rev"],
                                         display_name=display or None,
                                         fictional=fictional)
    return after


def remote_rev(name: str) -> int | None:
    """The record's current `rev`, or None if there is no such character.

    **Only a 404 is None.** Its ancestor caught every exception, which made a
    refusal indistinguishable from a missing bible — and a missing version
    disabled the conflict check, so a 403 turned the guard off rather than
    reporting it.
    """
    try:
        return int(resolve(name)["rev"])
    except api.NotFound:
        return None


# --- commands: the record --------------------------------------------------

@click.command("list")
@click.option("--json", "json_", is_flag=True)
def cmd_list(json_):
    """Every character in the library. **One query.**

    This listed the bucket's `characters/` prefix and called each folder a
    character. It is `query(pk = LIB#…, begins_with(sk, "CHARSLUG#"))` plus a
    batch read — so a folder somebody made by hand is a folder, and a character
    with no folder at all would still be listed.
    """
    found = entities.list_characters()
    if json_:
        print(json.dumps(found, indent=2))
    elif found:
        for record in found:
            counts = record.get("counts") or {}
            print(f"{record['slug']:<20} {record.get('display_name', ''):<24} "
                  f"refs {counts.get('references', 0):<5} files {counts.get('files', 0):<5} "
                  f"updated {str(record.get('updated', ''))[:10]}")
    else:
        print("(no characters yet — create one with `studio character create <name>`)",
              file=sys.stderr)


@click.command("show")
@click.argument("name", required=True)
@click.option("--json", "json_", is_flag=True)
@click.option("--profile", "profile_", is_flag=True, help="Print the bible as YAML.")
def cmd_show(name, json_, profile_):
    """A character's record: its id, its counts and the folders it actually has.

    The folder list is read off the root's children rather than printed from
    `POOLS`, because the four are a starting layout and a person may have
    renamed, deleted or added to them. Printing the convention would describe a
    character nobody has.
    """
    record = _require(name)
    if profile_:
        sys.stdout.write(yaml.safe_dump(document(record), sort_keys=False,
                                        allow_unicode=True, width=100))
        return
    if json_:
        print(json.dumps(record, indent=2))
        return
    counts = entities.references(record["id"]).get("counts") or {}
    folders = [f"{n['name']}/" for n in store.children_of(record["root"])
               if n.get("kind") == "folder"]
    print(f"{record['slug']}  ({record['id']})  rev {record.get('rev')}")
    print(f"  display   {record.get('display_name') or '—'}")
    print(f"  fictional {str(bool(record.get('fictional', True))).lower()}")
    print(f"  refs      {' · '.join(f'{g} {n}' for g, n in sorted(counts.items())) or '—'}"
          f"      default set: {len(record.get('default_set') or [])}")
    print(f"  root      {record['root']}   {' '.join(folders) or '(no folders)'}")


@click.command("create")
@click.argument("name", required=True)
@click.option("--display-name", "display_name", help="How the character is written in prose.")
@click.option("--dry-run", is_flag=True, help="With --shoot: render the payloads, submit nothing.")
@click.option("--from-profile", help="Local profile.yaml to seed with (default: blank template).")
@click.option("--model", help="With --shoot: override the shot spec's model.")
@click.option("--project", help="With --shoot: REQUIRED. The project the shoot's runs belong to.")
@click.option("--shoot", is_flag=True,
              help="Go straight into the standard reference shoot (asks before it bills).")
def cmd_create(name, display_name, dry_run, from_profile, model, project, shoot):
    """Create a character: the record, its slug claim, its root and four pools.

    **One transaction.** The pools used to appear lazily, on whatever write
    happened to need one first, so a character could exist with no `reference/`
    and the first `add-refs` would invent it. Either the whole character exists
    or none of it does.
    """
    check_name(name)
    src = from_profile or TEMPLATE
    if not os.path.isfile(src):
        die(f"profile source not found: {src}")
    data = parse_profile(read_text(src), src)
    if src != TEMPLATE:  # the template is deliberately unfilled; anything else must be real
        check_profile(data, src, name)
    if shoot and src == TEMPLATE:
        die("--shoot needs a real bible: the blank template has no wardrobe or consistency "
            "block to build a prompt from. Pass --from-profile.")

    profile, from_file, fictional = split_document(data)
    try:
        record = entities.create_character(name, display_name=display_name or from_file or name,
                                           fictional=fictional, profile=profile)
    except api.Conflict:
        die(f"character {name!r} already exists")
    made = [f"{n['name']}/" for n in store.children_of(record["root"])
            if n.get("kind") == "folder"]
    print(f"created character {record['slug']}  ({record['id']})")
    print("  " + "  ".join(made or [f"{p}/" for p in POOLS]))
    if src == TEMPLATE:
        print("  (blank template — fill it in with `edit`, then `set-profile`.)",
              file=sys.stderr)

    if not shoot:
        print(f"  next: seed photos with `studio character add-to {name} seed <img>...`, then\n"
              f"        the standard set with `studio character shoot {name} --project <p>`",
              file=sys.stderr)
        return 0

    # Deferred deliberately. The shoot invokes models and lives in `engine/`,
    # which imports this package — so importing it at module scope would point
    # the dependency arrow both ways. The character record stays ignorant of the
    # engine; only this one call knows about it.
    from types import SimpleNamespace

    from studio_pipeline.engine import shoot as SHOOT
    opts = SimpleNamespace(
        project=project, model=model, dry_run=dry_run,
        group="all", slot=(), identity="auto", identity_max=SHOOT.IDENTITY_MAX,
        pick=None, pick_tag=None, seed_pick=None, aspect_ratio=None, extra=None,
        review_sheet=None,
        dest=None,
    )
    try:
        return SHOOT.run_shoot(name, opts)
    except SHOOT.ShootError as exc:
        die(str(exc))


@click.command("delete")
@click.argument("name", required=True)
@click.option("--files", type=click.Choice(["keep", "delete"]), default="keep",
              help="What to do with the character's folder (default: keep it).")
@click.option("--force", is_flag=True,
              help="Delete even while projects or runs still name it.")
def cmd_delete(name, files, force):
    """Delete a character.

    **`--files keep` is the default deliberately.** The reverse default loses a
    reference library to a typo, and an orphaned folder in the library root is
    visible and recoverable; nothing this service does to S3 is undoable.

    **The refusal is the interesting half, and `--force` is right here** — which
    is not true of `projects delete --force`. A project or a run that names this
    character holds a link row, and those rows are what make "every run of this
    subject" answerable. But a run is HISTORY: it really did use this character,
    and deleting the character is not a reason to delete the work. So force
    drops the links and leaves the runs, where the same flag on a project would
    leave children naming a parent that is gone.
    """
    record = _require(name)
    try:
        entities.delete_character(record["id"], files=files, force=force)
    except api.Conflict as exc:
        die(f"{exc}\n       pass --force to drop those links and delete it anyway")
    print(f"deleted character {record['slug']} (files: {files})")


@click.command("rename")
@click.argument("name", required=True)
@click.argument("new", required=True)
def cmd_rename(name, new):
    """Give a character a new slug. **ONE conditional write.**

    Four operations inside one transaction: the old claim goes, the new one is
    written under `attribute_not_exists`, the record updates, and the root
    folder node is renamed. Nothing else in the library is touched.

    This was the worst command in the pipeline and it is worth saying what it
    did. `rename.py` listed all four pools, `PATCH`ed every basename that
    carried the slug, rewrote the bible's `references:` map to match the new
    basenames, then swept every run document in every project rewriting the
    paths they had recorded — and was a dry run by default because getting it
    wrong stranded records. `domain/rewrite.py` existed for that sweep. Every
    line of it is deleted: a record names a **node id**, and a node id survives a
    rename by construction.
    """
    record = _require(name)
    check_name(new)
    try:
        after = entities.patch_character(record["id"], record["rev"], slug=new)
    except api.Conflict as exc:
        die(str(exc))
    refs = len(entities.reference_entries(record["id"]))
    print(f"renamed {record['slug']} → {after['slug']}")
    print(f"  0 objects copied · 0 records rewritten · {refs} references untouched")


@click.command("textblock")
@click.argument("name", required=True)
def cmd_textblock(name):
    """A pasteable identity paragraph, for engines driven from a start frame.

    Seedance and Kling-on-Replicate both carry identity through
    `reference_images`; when driving from a start frame instead, the character
    has to survive as PROSE in the prompt. `GET /api/characters/<id>/textblock`
    answers with the authored block when the bible has one, and with the
    identity-bearing sections as raw material when it does not — the API
    decides which, so the CLI and the SPA cannot paste different paragraphs
    into the same model.
    """
    record = _require(name)
    found = entities.textblock(record["id"])
    authored = (found.get("text") or "").strip()
    # No `<`-check here any more: the route empties an unfilled `<>` before it
    # answers, so the branch is `text` or nothing. It used to be tested here and
    # `raw` used to arrive empty from a route that never sent it, which is how
    # this printed `{}` and told you to compress it.
    if authored:
        print(authored)
        print(f"\n(authored block from {record['slug']}'s bible)", file=sys.stderr)
        return

    sys.stdout.write(yaml.safe_dump(found.get("raw") or {}, sort_keys=False,
                                    allow_unicode=True, width=88))
    print(
        f"\nNo authored `text_identity_block` in {record['slug']}'s bible — the above is raw "
        "material.\nCompress it into ONE paragraph of ~50-70 words covering only what a "
        "text-only engine\ncannot infer: build proportion, hair, face landmarks, skin, and "
        "signature accessories.\nThen save it back into the bible under `text_identity_block:` "
        f"(`studio character edit {record['slug']}`)\nso it is written once and reused.\n"
        "\nNOTE: with a start frame supplied, keep the pasted block SHORT — the frame carries\n"
        "appearance better than prose, and a long block fights it (see studio-media-kling).",
        file=sys.stderr,
    )


@click.command("set-profile")
@click.argument("name", required=True)
@click.argument("file", required=False)
def cmd_set_profile(name, file):
    """Replace the bible. With no FILE, pushes the local working copy.

    `PATCH /api/characters/<id>/profile` with the `rev` last seen. FILE omitted is
    the `edit` round trip's second half and uses the `rev` recorded at pull
    time, so a stale copy is refused; FILE given is an assertion and uses the
    record's current `rev`, which the API still compare-and-swaps against.
    """
    record = _require(name)
    if file is None:
        local, base, revf = local_paths(record["slug"])
        do_push(record["slug"], False, local, base, revf)
        return
    if not os.path.isfile(file):
        die(f"profile file not found: {file}")
    data = parse_profile(read_text(file), file)
    check_profile(data, file, record["slug"])
    after = save_profile(record, data)
    print(f"profile updated (rev {record['rev']} → {after['rev']})", file=sys.stderr)


# --- local round-trip editing (`edit`) ------------------------------------
#
# Three files per character under local/characters/ (all git-ignored):
#   <name>.yaml         the working copy you edit
#   .<name>.base.yaml   pristine copy as pulled — used to detect your edits + diff
#   .<name>.rev         the record's `rev` at pull time — sent back as the CAS
#                       value, so a push of a stale copy is refused by the API
#                       rather than compared here. It held an S3 ETag, then the
#                       node's `updated_at`; both were check-then-write.

def local_paths(name: str, override: str | None = None) -> tuple[str, str, str]:
    """(working copy, base copy, rev file) for a character."""
    path = os.path.abspath(override) if override else os.path.join(LOCAL_DIR, f"{name}.yaml")
    d, stem = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
    return path, os.path.join(d, f".{stem}.base.yaml"), os.path.join(d, f".{stem}.rev")


def fetch_profile(name: str) -> tuple[str, str]:
    """(the bible as YAML text, the `rev` it was read at).

    **One call, and the two cannot disagree.** This was two — the bytes from a
    presigned URL and the version off the node record — with a careful argument
    about which to read first so that a write landing between them produced a
    refusal rather than an overwrite. The record carries both, so the ordering
    problem does not exist.
    """
    record = _require(name)
    text = yaml.safe_dump(document(record), sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=100)
    return text, str(record["rev"])


def unified(before: str, after: str, name: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{name} (stored bible)",
            tofile=f"local/{name}.yaml",
        )
    )


def do_pull(name: str, force: bool, local: str, base: str, revf: str) -> None:
    text, rev = fetch_profile(name)
    if os.path.exists(local) and not force:
        current = read_text(local)
        prior = read_text(base) if os.path.exists(base) else None
        if current != (prior if prior is not None else text):
            die(
                f"local copy has unsaved edits: {local}\n"
                "  push them first (re-run without --pull), or discard them with --discard."
            )
    write_text(local, text)
    write_text(base, text)
    write_text(revf, rev)
    print(local)  # stdout: pipeable, e.g. `code "$(... edit <name>)"`
    print(
        f"wrote {local} (rev {rev})\n"
        f"  edit the file above, then: studio character set-profile {name}",
        file=sys.stderr,
    )


def do_push(name: str, force: bool, local: str, base: str, revf: str) -> None:
    if not os.path.isfile(local):
        die(f"no local copy at {local} — run `edit {name}` first to pull it.")
    text = read_text(local)
    prior = read_text(base) if os.path.exists(base) else None

    if prior is None and not force:
        die(
            f"no pull record for {local} (missing {os.path.basename(base)}), so the revision\n"
            "  it was taken at is unknown. Re-run with --force to write at the current one."
        )
    if prior is not None and text == prior:
        print(f"no local changes in {local} — nothing to upload.", file=sys.stderr)
        return

    # A bible that no longer parses, or has lost a schema key, is worse than no
    # write at all — every downstream reader breaks on it. Check before the write.
    data = parse_profile(text, local)
    check_profile(data, local, name)

    record = _require(name)
    recorded = read_text(revf).strip() if os.path.exists(revf) else ""
    # The recorded rev is the point of the sidecar: sending it makes the API
    # refuse a push built on a copy someone else has since written over. `--force`
    # sends the record's own rev instead, which always succeeds.
    rev = record["rev"] if (force or not recorded) else int(recorded)

    if prior is not None:
        sys.stderr.write(unified(prior, text, name))
    after = save_profile(record, data, rev)
    write_text(base, text)
    write_text(revf, str(after["rev"]))
    print(f"profile updated (rev {rev} → {after['rev']})", file=sys.stderr)


@click.command("edit")
@click.argument("name", required=True)
@click.option("--diff", is_flag=True, help="Show local-vs-stored differences and exit.")
@click.option("--discard", is_flag=True, help="Throw away local edits and re-pull.")
@click.option("--force", is_flag=True, help="Proceed despite unsaved edits or a changed record.")
# **Relative, not `LOCAL_DIR`.** Interpolating the absolute path put the
# author's home directory into the help string, and from there into
# `cli_surface_reference.json` — a contract that then only matched on the
# machine it was captured on, and failed in CI with a diff of two absolute
# paths. Help text is documentation; it should read the same everywhere.
@click.option("--path",
              help="Working-copy path (default: studio/local/characters/<name>.yaml).")
@click.option("--pull", is_flag=True, help="Force the download direction.")
@click.option("--push", is_flag=True, help="Force the upload direction.")
def cmd_edit(name, diff, discard, force, path, pull, push):
    """Round-trip the bible through local/characters/<name>.yaml.

    The document is assembled from the record, not downloaded — there is no
    `profile.yaml` in the bucket any more — and pushed back as
    `PATCH …/profile {profile, rev}`.
    """
    check_name(name)
    local, base, revf = local_paths(name, path)

    if discard:
        force = True
        do_pull(name, force, local, base, revf)
        return

    if diff:
        if not os.path.isfile(local):
            die(f"no local copy at {local} — run `edit {name}` first to pull it.")
        remote, _rev = fetch_profile(name)
        # `text`, not `diff`. The flag was rebound to the diff itself, so the
        # `if not diff` below asked about the text while reading as though it
        # asked about the option. Harmless here — inside this branch the flag is
        # already known true — but it is the `--keys` bug's exact shape, and
        # `test_cli_shadowing` refuses it rather than judging each case.
        text = unified(remote, read_text(local), name)
        sys.stdout.write(text)
        if not text:
            print(f"{local} matches the stored bible.", file=sys.stderr)
        return

    # Direction: explicit flags win; otherwise pull when there is no working copy
    # yet, push once there is one. That makes the flow "run, edit, run again".
    if pull:
        do_pull(name, force, local, base, revf)
    elif push or os.path.isfile(local):
        do_push(name, force, local, base, revf)
    else:
        do_pull(name, force, local, base, revf)


def _require(name: str) -> dict:
    """The record, or a message naming the command that lists the real options."""
    try:
        return resolve(name)
    except api.NotFound:
        die(f"no character {name!r} (see `studio character list`)")
