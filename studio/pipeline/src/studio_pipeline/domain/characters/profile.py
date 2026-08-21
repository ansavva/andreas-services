"""The bible: its schema, reading and writing it, and the local round trip.

`profile.yaml` is the SOURCE OF TRUTH for a character — who they are, plus the
described index of their reference library (which `refs.py` owns the operations
on). Everything here is about the document itself.

THE CONFLICT CHECK, AND WHAT REPLACED THE ETAG
----------------------------------------------
A bible is edited in two ways at once — by a person through `edit`, and by the
index commands (`add-refs`, `describe-refs`, `set-ref-desc`, `default-set`,
`sync-refs`) — so both record a version when they read and refuse to write if it
has moved. Without it a `--push` of a local copy pulled an hour ago silently
reverts every description written since.

**It was the S3 ETag. It is now the node's `updated_at`**, because the catalog
exposes no ETag and deliberately never will: `blob_key` does not leave the API,
so there is nothing content-addressed for a client to compare.

`updated_at` is a sound substitute and the reasoning is worth keeping:

- **Microsecond resolution** (`catalog._now`), so two writes cannot share a
  value the way they could under S3's one-second `LastModified`. That was the
  objection to using a timestamp and it does not apply.
- **It moves on every write to the blob**, which is what the check needs.
- **It also moves on a rename or a move, which touch no bytes.** That is a
  false refusal — the check fires when it need not have. It errs toward
  refusing, tells the reader to re-run, and loses nothing; an ETag erred the
  same way for a metadata-only copy.

What it is NOT is a content hash: two writes of identical bytes produce
different values where an ETag produced the same one. Nothing here wanted that
property — the question asked is "did anyone write since I read", not "are the
bytes the ones I saw".
"""
from __future__ import annotations

import difflib
import os
import sys

import click
import yaml

from studio_pipeline.adapters import api, store
from studio_pipeline.domain import paths as P
from studio_pipeline.domain.characters.base import (
    LOCAL_DIR,
    PROFILE_CT,
    PROFILE_FILE,
    TEMPLATE,
    check_name,
    die,
    profile_key,
    put_file,
    read_text,
    write_text,
)

# --- the bible schema -----------------------------------------------------
#
# Every character carries the SAME top-level keys (templates/profile.yaml), so
# anything downstream reads a path — `consistency.must`, `identity.build` —
# instead of pattern-matching headings out of prose. Missing keys are refused on
# upload: a bible with no `consistency` block is a bible that silently stops
# being checked against.
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
    "references",
    "default_set",
    "consistency",
    "text_identity_block",
)
# Identity-bearing keys, in the order a text block wants them. Voice, rendering
# and the schema bookkeeping don't survive into one and are dropped.
TEXTBLOCK_KEYS = ("identity", "face", "body", "wardrobe", "consistency")


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
    """Refuse a bible that has drifted off the shared schema."""
    missing = [k for k in PROFILE_KEYS if k not in data]
    if missing:
        die(
            f"{where} is missing required key(s): {', '.join(missing)}\n"
            "  every character carries the same schema — see templates/profile.yaml."
        )
    extra = [k for k in data if k not in PROFILE_KEYS]
    if extra:
        print(
            f"warning: {where} has key(s) outside the schema: {', '.join(extra)}",
            file=sys.stderr,
        )
    if name and data.get("name") != name:
        die(f"{where} declares name: {data.get('name')!r}, but this is character {name!r}.")


def load_profile(name: str) -> dict:
    path = profile_key(name)
    try:
        text = store.read(path).decode("utf-8")
    except api.NotFound:
        die(f"no {PROFILE_FILE} for character {name!r} (looked at {path}).")
    return parse_profile(text, path)


def write_profile(name: str, data: dict, version: str | None = None) -> None:
    """Put a bible back, refusing if it changed underneath us.

    Every index command goes through here, so a description written while
    someone else was editing the bible fails loudly instead of silently
    dropping their edit.

    **Check-then-write, not a conditional write.** There is a window between the
    two in which someone else's write can land and be lost. It was there under
    the ETag as well — S3 had no compare-and-swap either — and closing it means
    an `If-Match` on the API, which is a route change and not this one. The
    window is microseconds against a document a human edits.
    """
    if version is not None and remote_version(name) != version:
        die(f"{name}'s profile.yaml changed since it was read — re-run to pick up "
            "the new version rather than overwriting it.")
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=100)
    store.folder(P.character_prefix(name))
    store.write(profile_key(name), text.encode("utf-8"), content_type=PROFILE_CT)


@click.command("show")
@click.argument("name", required=True)
def cmd_show(name):
    check_name(name)
    path = profile_key(name)
    try:
        body = store.read(path)
    except api.NotFound:
        die(f"no {PROFILE_FILE} for character {name!r} (looked at {path}).")
    sys.stdout.write(body.decode("utf-8"))


@click.command("textblock")
@click.argument("name", required=True)
def cmd_textblock(name):
    """Emit a pasteable text identity block for engines with no reference system.

    Seedance and Kling-on-Replicate both carry identity through `reference_images`;
    when driving from a start frame instead, the character has to survive as
    PROSE in the prompt. If the bible has an authored `text_identity_block` that
    is the canonical answer and is printed verbatim. Otherwise this prints the
    identity-bearing keys as raw material to compress — the script can't write
    prose.
    """
    check_name(name)
    data = load_profile(name)

    authored = (data.get("text_identity_block") or "").strip()
    if authored and not authored.startswith("<"):  # "<>" is the unfilled template
        print(authored)
        print(f"\n(authored block from {name}'s bible)", file=sys.stderr)
        return

    raw = {k: data[k] for k in TEXTBLOCK_KEYS if data.get(k)}
    sys.stdout.write(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=88))

    print(
        f"\nNo authored `text_identity_block` in {name}'s bible — the above is raw "
        "material.\nCompress it into ONE paragraph of ~50-70 words covering only what a "
        "text-only engine\ncannot infer: build proportion, hair, face landmarks, skin, and "
        "signature accessories.\nThen save it back into the bible under `text_identity_block:` "
        f"(`studio character edit {name}`)\nso it is written once and reused.\n"
        "\nNOTE: with a start frame supplied, keep the pasted block SHORT — the frame carries\n"
        "appearance better than prose, and a long block fights it (see studio-media-kling).",
        file=sys.stderr,
    )


@click.command("create")
@click.argument("name", required=True)
@click.option("--dry-run", is_flag=True, help="With --shoot: render the payloads, submit nothing.")
@click.option("--from-profile", help="Local profile.yaml to seed with (default: blank template).")
@click.option("--model", help="With --shoot: override the shot spec's model.")
@click.option("--project", help="With --shoot: REQUIRED. The project the shoot's runs belong to.")
@click.option("--shoot", is_flag=True,
              help="Go straight into the standard reference shoot (asks before it bills).")
def cmd_create(name, dry_run, from_profile, model, project, shoot):
    check_name(name)
    src = from_profile or TEMPLATE
    if not os.path.isfile(src):
        die(f"profile source not found: {src}")
    if src != TEMPLATE:  # the template is deliberately unfilled; anything else must be real
        check_profile(parse_profile(read_text(src), src), src, name)
    if shoot and src == TEMPLATE:
        die("--shoot needs a real bible: the blank template has no wardrobe or consistency "
            "block to build a prompt from. Pass --from-profile.")
    path = put_file(src, profile_key(name), PROFILE_CT)
    print(f"created character {name!r}: {path}", file=sys.stderr)
    if src == TEMPLATE:
        print("  (blank template — fill it in, then `set-profile` the result.)", file=sys.stderr)

    if not shoot:
        print(f"  next: seed photos with `studio character add-to {name} seed <img>...`, then\n"
              f"        the standard set with `studio character shoot {name} --project <p>`",
              file=sys.stderr)
        return 0

    # Deferred deliberately. The shoot invokes models and lives in `engine/`,
    # which imports this module — so importing it at module scope would point the
    # dependency arrow both ways. The character store stays ignorant of the
    # engine; only this one call knows about it.
    from types import SimpleNamespace

    from studio_pipeline.engine import shoot as SHOOT
    opts = SimpleNamespace(
        project=project, model=model, dry_run=dry_run,
        group="all", slot=(), identity="auto", identity_max=SHOOT.IDENTITY_MAX,
        pick=None, pick_tag=None, seed_pick=None, aspect_ratio=None, extra=None,
        review_sheet=None,
        dest=None, expires=3600,
    )
    try:
        return SHOOT.run_shoot(name, opts)
    except SHOOT.ShootError as exc:
        die(str(exc))


@click.command("set-profile")
@click.argument("file", required=True)
@click.argument("name", required=True)
def cmd_set_profile(file, name):
    check_name(name)
    if not os.path.isfile(file):
        die(f"profile file not found: {file}")
    check_profile(parse_profile(read_text(file), file), file, name)
    print(f"updated {put_file(file, profile_key(name), PROFILE_CT)}", file=sys.stderr)


# --- local round-trip editing (`edit`) ------------------------------------
#
# Three files per character under local/characters/ (all git-ignored):
#   <name>.yaml         the working copy you edit
#   .<name>.base.yaml   pristine copy as pulled — used to detect your edits + diff
#   .<name>.etag        S3 ETag at pull time — used to detect edits made elsewhere

def local_paths(name: str, override: str | None = None) -> tuple[str, str, str]:
    """(working copy, base copy, etag file) for a character."""
    path = os.path.abspath(override) if override else os.path.join(LOCAL_DIR, f"{name}.yaml")
    d, stem = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
    return path, os.path.join(d, f".{stem}.base.yaml"), os.path.join(d, f".{stem}.etag")


def fetch_profile(name: str) -> tuple[str, str]:
    """(text, version) of the stored profile.yaml.

    Two calls where this was one: the bytes come from a presigned URL and the
    version off the node record, and no single route hands out both. Read the
    version FIRST — a write landing between the two then produces a version
    older than the text, so the next push refuses and re-reads. The other order
    would produce a version NEWER than the text, and a push would overwrite the
    write it never saw.
    """
    path = profile_key(name)
    version = remote_version(name)
    try:
        return store.read(path).decode("utf-8"), version or ""
    except api.NotFound:
        die(f"no {PROFILE_FILE} for character {name!r} (looked at {path}).")
        raise  # unreachable; `die` exits. Here so the return type is honest.


def remote_version(name: str) -> str | None:
    """The node's `updated_at`, or None if there is no node.

    **Only a 404 is None.** This caught every exception, which made a refusal
    indistinguishable from a missing bible — and a missing version disables the
    conflict check (`if recorded and current and ...`), so a 403 would have
    turned the guard off rather than reporting it.
    """
    try:
        return store.resolve(profile_key(name)).get("updated_at")
    except api.NotFound:
        return None


def unified(before: str, after: str, name: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{name}/{PROFILE_FILE}",
            tofile=f"local/{name}.yaml",
        )
    )


def do_pull(name: str, force: bool, local: str, base: str, etagf: str) -> None:
    text, version = fetch_profile(name)
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
    write_text(etagf, version)
    print(local)  # stdout: pipeable, e.g. `code "$(... edit <name>)"`
    print(
        f"pulled {profile_key(name)}\n"
        f"  edit the file above, then re-run `edit {name}` to upload it.",
        file=sys.stderr,
    )


def do_push(name: str, force: bool, local: str, base: str, etagf: str) -> None:
    if not os.path.isfile(local):
        die(f"no local copy at {local} — run `edit {name}` first to pull it.")
    text = read_text(local)
    prior = read_text(base) if os.path.exists(base) else None

    if prior is None and not force:
        die(
            f"no pull record for {local} (missing {os.path.basename(base)}), so edits made\n"
            "  elsewhere cannot be detected. Re-run with --force to upload anyway."
        )
    if prior is not None and text == prior:
        print(f"no local changes in {local} — nothing to upload.", file=sys.stderr)
        return

    recorded = read_text(etagf).strip() if os.path.exists(etagf) else None
    current = remote_version(name)
    if recorded and current and recorded != current and not force:
        die(
            f"the stored {PROFILE_FILE} for {name!r} changed since you pulled it — uploading would\n"
            "  discard that change. Re-run with --force to overwrite, or --discard to\n"
            "  throw away your local edits and re-pull."
        )

    # A bible that no longer parses, or has lost a schema key, is worse than no
    # upload at all — every downstream reader breaks on it. Check before the PUT.
    check_profile(parse_profile(text, local), local, name)

    if prior is not None:
        sys.stderr.write(unified(prior, text, name))
    # `profile_key`, never a hand-built path. This line read
    # f"{name}/{PROFILE_FILE}" — the pre-migration layout — so every push landed
    # at `<name>/profile.yaml` in the bucket root instead of under `characters/`,
    # reported success, and wrote the local sidecars as though it had worked. The
    # bible was never updated and nothing said so.
    path = put_file(local, profile_key(name), PROFILE_CT)
    write_text(base, text)
    write_text(etagf, remote_version(name) or "")
    print(f"uploaded {path}", file=sys.stderr)


@click.command("edit")
@click.argument("name", required=True)
@click.option("--diff", is_flag=True, help="Show local-vs-S3 differences and exit.")
@click.option("--discard", is_flag=True, help="Throw away local edits and re-pull.")
@click.option("--force", is_flag=True, help="Proceed despite unsaved edits or a changed remote.")
@click.option("--path", help=("Working-copy path (default: "
              "/Users/andreassavva/repos/andreas-services/studio/local/characters/<name>.yaml)."))
@click.option("--pull", is_flag=True, help="Force the download direction.")
@click.option("--push", is_flag=True, help="Force the upload direction.")
def cmd_edit(name, diff, discard, force, path, pull, push):
    check_name(name)
    local, base, etagf = local_paths(name, path)

    if discard:
        force = True
        do_pull(name, force, local, base, etagf)
        return

    if diff:
        if not os.path.isfile(local):
            die(f"no local copy at {local} — run `edit {name}` first to pull it.")
        remote, _ = fetch_profile(name)
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
        do_pull(name, force, local, base, etagf)
    elif push or os.path.isfile(local):
        do_push(name, force, local, base, etagf)
    else:
        do_pull(name, force, local, base, etagf)

