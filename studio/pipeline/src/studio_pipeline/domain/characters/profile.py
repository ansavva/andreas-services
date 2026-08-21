"""The bible: its schema, reading and writing it, and the local round trip.

`profile.yaml` is the SOURCE OF TRUTH for a character — who they are, plus the
described index of their reference library (which `refs.py` owns the operations
on). Everything here is about the document itself.

**The ETag is the conflict check**, and it is the one thing in this file that
does not survive the move onto the API unchanged: `remote_etag` is an S3 concept
and the catalog does not expose one. `edit --push` and every index write refuse
when it has moved, so a bible edited in two places fails loudly instead of one
edit silently winning. Replacing it needs a decision, not a substitution — see
the `#305` follow-up.
"""
from __future__ import annotations

import difflib
import os
import sys

import click
import yaml

from studio_pipeline.adapters import s3 as s3c
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


def load_profile(s3, name: str) -> dict:
    key = profile_key(name)
    try:
        text = s3.get_object(Bucket=s3c.BUCKET, Key=key)["Body"].read().decode("utf-8")
    except s3.exceptions.NoSuchKey:
        die(f"no {PROFILE_FILE} for character {name!r} (looked at s3://{s3c.BUCKET}/{key}).")
    return parse_profile(text, f"s3://{s3c.BUCKET}/{key}")


def write_profile(s3, name: str, data: dict, etag: str | None = None) -> None:
    """Put a bible back, refusing if it changed underneath us.

    Every index command goes through here, so a description written while
    someone else was editing the bible fails loudly instead of silently
    dropping their edit.
    """
    if etag is not None and remote_etag(s3, name) != etag:
        die(f"{name}'s profile.yaml changed in S3 since it was read — re-run to pick up "
            "the new version rather than overwriting it.")
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=100)
    s3.put_object(Bucket=s3c.BUCKET, Key=profile_key(name),
                  Body=text.encode("utf-8"), ContentType=PROFILE_CT)


@click.command("show")
@click.argument("name", required=True)
def cmd_show(name):
    s3 = s3c.client()
    check_name(name)
    key = profile_key(name)
    try:
        body = s3.get_object(Bucket=s3c.BUCKET, Key=key)["Body"].read()
    except s3.exceptions.NoSuchKey:
        die(f"no {PROFILE_FILE} for character {name!r} (looked at s3://{s3c.BUCKET}/{key}).")
    sys.stdout.write(body.decode("utf-8"))


@click.command("textblock")
@click.argument("name", required=True)
def cmd_textblock(name):
    s3 = s3c.client()
    """Emit a pasteable text identity block for engines with no reference system.

    Seedance and Kling-on-Replicate both carry identity through `reference_images`;
    when driving from a start frame instead, the character has to survive as
    PROSE in the prompt. If the bible has an authored `text_identity_block` that
    is the canonical answer and is printed verbatim. Otherwise this prints the
    identity-bearing keys as raw material to compress — the script can't write
    prose.
    """
    check_name(name)
    data = load_profile(s3, name)

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
    s3 = s3c.client()
    check_name(name)
    src = from_profile or TEMPLATE
    if not os.path.isfile(src):
        die(f"profile source not found: {src}")
    if src != TEMPLATE:  # the template is deliberately unfilled; anything else must be real
        check_profile(parse_profile(read_text(src), src), src, name)
    if shoot and src == TEMPLATE:
        die("--shoot needs a real bible: the blank template has no wardrobe or consistency "
            "block to build a prompt from. Pass --from-profile.")
    uri = put_file(s3, src, profile_key(name), PROFILE_CT)
    print(f"created character {name!r}: {uri}", file=sys.stderr)
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
    s3 = s3c.client()
    check_name(name)
    if not os.path.isfile(file):
        die(f"profile file not found: {file}")
    check_profile(parse_profile(read_text(file), file), file, name)
    uri = put_file(s3, file, profile_key(name), PROFILE_CT)
    print(f"updated {uri}", file=sys.stderr)


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


def fetch_profile(s3, name: str) -> tuple[str, str]:
    """(text, etag) of the remote profile.yaml."""
    key = profile_key(name)
    try:
        obj = s3.get_object(Bucket=s3c.BUCKET, Key=key)
    except s3.exceptions.NoSuchKey:
        die(f"no {PROFILE_FILE} for character {name!r} (looked at s3://{s3c.BUCKET}/{key}).")
    return obj["Body"].read().decode("utf-8"), obj["ETag"].strip('"')


def remote_etag(s3, name: str) -> str | None:
    try:
        return s3.head_object(Bucket=s3c.BUCKET, Key=profile_key(name))["ETag"].strip('"')
    except Exception:
        return None


def unified(before: str, after: str, name: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"s3://{name}/{PROFILE_FILE}",
            tofile=f"local/{name}.yaml",
        )
    )


def do_pull(s3, name: str, force: bool, local: str, base: str, etagf: str) -> None:
    text, etag = fetch_profile(s3, name)
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
    write_text(etagf, etag)
    print(local)  # stdout: pipeable, e.g. `code "$(... edit <name>)"`
    print(
        f"pulled s3://{s3c.BUCKET}/{profile_key(name)}\n"
        f"  edit the file above, then re-run `edit {name}` to upload it.",
        file=sys.stderr,
    )


def do_push(s3, name: str, force: bool, local: str, base: str, etagf: str) -> None:
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
    current = remote_etag(s3, name)
    if recorded and current and recorded != current and not force:
        die(
            f"s3 {PROFILE_FILE} for {name!r} changed since you pulled it — uploading would\n"
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
    uri = put_file(s3, local, profile_key(name), PROFILE_CT)
    write_text(base, text)
    write_text(etagf, remote_etag(s3, name) or "")
    print(f"uploaded {uri}", file=sys.stderr)


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
    s3 = s3c.client()
    check_name(name)
    local, base, etagf = local_paths(name, path)

    if discard:
        force = True
        do_pull(s3, name, force, local, base, etagf)
        return

    if diff:
        if not os.path.isfile(local):
            die(f"no local copy at {local} — run `edit {name}` first to pull it.")
        remote, _ = fetch_profile(s3, name)
        diff = unified(remote, read_text(local), name)
        sys.stdout.write(diff if diff else "")
        if not diff:
            print(f"{local} matches s3.", file=sys.stderr)
        return

    # Direction: explicit flags win; otherwise pull when there is no working copy
    # yet, push once there is one. That makes the flow "run, edit, run again".
    if pull:
        do_pull(s3, name, force, local, base, etagf)
    elif push or os.path.isfile(local):
        do_push(s3, name, force, local, base, etagf)
    else:
        do_pull(s3, name, force, local, base, etagf)

