"""`studio character` — manage on-model characters stored in the
xharness-prod-media-us-east-1 S3 bucket.

A character is DATA, not a skill: each one is an S3 record under
`characters/<name>/` (see the `studio-media-s3` skill), and this one tool manages them all:

    characters/<name>/profile.yaml   the bible (SOURCE OF TRUTH), including the
                                     DESCRIBED index of the reference library
    characters/<name>/reference/     generated character imagery, in purpose
                                     subfolders: face/ body/ wardrobe/ scene/ …
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

Examples:
  studio character create <name> --from-profile /tmp/<name>.yaml
  studio character add-refs <name> --to face /tmp/*.png
  studio character refs <name> --describe
  studio character refs <name> --pick-tag face --presign --json
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import tempfile

import click
import yaml

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.domain import paths as P
# For `add-refs --from-run`: resolving a runref to its output keys. One-way —
# the run store knows nothing about characters.
from studio_pipeline.domain import runs as R

PROFILE_FILE = "profile.yaml"
PROFILE_CT = "application/yaml"
TEMPLATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "templates", PROFILE_FILE
)
# Working copies for `edit` live in the repo (git-ignored) so they are easy to
# open in an editor: <repo>/local/characters/<name>.yaml
LOCAL_DIR = str(STUDIO_DIR / "local" / "characters")
NAME_RE = P.NAME_RE


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


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


def pool_max_index(s3, name: str, pool: str, group: str | None = None) -> int:
    """Highest N among numbered files in a pool (optionally one subfolder)."""
    pat = re.compile(rf"^{re.escape(group_prefix(name, group))}(\d+)\.")
    folder = pool_folder(name, pool) + (f"/{group}" if group else "")
    hi = 0
    for key in s3c.list_keys(s3, folder):
        if group is None and "/" in key[len(s3c.key(folder)) + 1:]:
            continue  # a subfolder numbers itself
        if (m := pat.match(os.path.basename(key))):
            hi = max(hi, int(m.group(1)))
    return hi


def put_file(s3, local: str, key: str, content_type: str | None = None) -> str:
    import mimetypes

    ct = content_type or mimetypes.guess_type(local)[0] or "application/octet-stream"
    s3.upload_file(local, s3c.BUCKET, key, ExtraArgs={"ContentType": ct})
    return f"s3://{s3c.BUCKET}/{key}"


# --- subcommands ----------------------------------------------------------

@click.group(help=__doc__)
def main():
    pass


@main.command("list")
@click.option("--json", "json_", is_flag=True)
def cmd_list(json_):
    s3 = s3c.client()
    names = P.list_characters(s3)
    if json_:
        print(json.dumps(names, indent=2))
    elif names:
        print("\n".join(names))
    else:
        print("(no characters yet — create one with `studio character create <name>`)", file=sys.stderr)


@main.command("show")
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


@main.command("textblock")
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


@main.command("create")
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


@main.command("set-profile")
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

def profile_key(name: str) -> str:
    return P.profile_key(name)


def local_paths(name: str, override: str | None = None) -> tuple[str, str, str]:
    """(working copy, base copy, etag file) for a character."""
    path = os.path.abspath(override) if override else os.path.join(LOCAL_DIR, f"{name}.yaml")
    d, stem = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
    return path, os.path.join(d, f".{stem}.base.yaml"), os.path.join(d, f".{stem}.etag")


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


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


@main.command("edit")
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


# --- the reference index --------------------------------------------------
#
# `reference/` holds far more images than any model accepts, so something has to
# say WHICH ones to send. That something is the bible: `references:` describes
# every image, and `default_set:` names the ones sent when nothing is picked.
#
# The index is also what makes slots work now that reference/ has subfolders.
# Slot N used to be the trailing number in a flat folder; it is now position N
# in the RESOLVED SELECTION, so [Image1] means "the first image actually sent"
# regardless of where it lives or what it is called.

IMG_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}


def ref_root(name: str) -> str:
    return s3c.key(pool_folder(name, "reference")) + "/"


def ref_files(s3, name: str) -> list[str]:
    """Every image in reference/, as paths relative to it. Sidecars excluded."""
    root = ref_root(name)
    return [k[len(root):] for k in s3c.list_keys(s3, pool_folder(name, "reference"))
            if os.path.splitext(k)[1].lower() in IMG_EXTS]


def _sidecar_caption(s3, image_key: str) -> str:
    """Text of the <basename>.txt sidecar next to an image key, or '' if none.

    Predates the profile index. Kept as a fallback so a character whose
    descriptions were only ever written as sidecars still reads sensibly.
    """
    txt_key = os.path.splitext(image_key)[0] + ".txt"
    try:
        return s3.get_object(Bucket=s3c.BUCKET, Key=txt_key)["Body"].read().decode("utf-8").strip()
    except s3.exceptions.NoSuchKey:
        return ""
    except Exception:
        return ""


def read_index(s3, name: str) -> tuple[dict, list[dict]]:
    """(profile, references) — the index as the bible currently records it."""
    data = load_profile(s3, name)
    entries = data.get("references") or []
    if not isinstance(entries, list):
        die(f"{name}'s `references:` must be a list of {{file, description, tags}} entries")
    return data, entries


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


def resolve_selection(s3, name: str, pick: list[str] | None = None,
                      tags: list[str] | None = None,
                      slots: list[int] | None = None) -> list[str]:
    """Which reference images to send, as S3 keys, in index order.

    Resolution order: --pick names > --pick-tag > default_set > everything.
    The last of those is a fallback, not a default worth relying on: a character
    with a large reference/ and no default_set will overrun every model's cap,
    and the caller is expected to say so rather than truncate.
    """
    _data, entries = read_index(s3, name)
    by_file = {e.get("file"): e for e in entries if e.get("file")}
    root = ref_root(name)

    if pick:
        chosen = []
        for want in pick:
            hit = by_file.get(want) or next(
                (e for f, e in by_file.items()
                 if os.path.splitext(os.path.basename(f))[0] == want), None)
            if not hit:
                die(f"{name} has no reference {want!r}. See `studio character refs {name} --describe`.")
            chosen.append(hit["file"])
    elif tags:
        want = set(tags)
        chosen = [e["file"] for e in entries if want <= set(e.get("tags") or [])]
        if not chosen:
            have = sorted({t for e in entries for t in (e.get("tags") or [])})
            die(f"no reference of {name} carries all of {sorted(want)}. Tags in use: {have or '(none)'}")
    else:
        data, _ = read_index(s3, name)
        chosen = list(data.get("default_set") or []) or [e["file"] for e in entries]
        if not chosen:
            chosen = ref_files(s3, name)

    keys = [root + f for f in chosen]
    if slots:
        try:
            keys = [keys[i - 1] for i in slots]
        except IndexError:
            die(f"--slots out of range: the selection has {len(keys)} image(s)")
    return keys


def sync_index(s3, name: str, *, rename_map: dict[str, str] | None = None,
               apply: bool = True) -> dict:
    """Reconcile `references:` against what is actually in reference/.

    Renames are FOLLOWED rather than re-derived, so a description stays with its
    image when curate.py renumbers or moves one. A file that has vanished is
    marked `missing: true` rather than dropped — losing a written description
    because an object moved is worse than carrying a stale entry.
    """
    data, entries = read_index(s3, name)
    etag = remote_etag(s3, name)
    for e in entries:
        if rename_map and e.get("file") in rename_map:
            e["file"] = rename_map[e["file"]]

    on_disk = ref_files(s3, name)
    known = {e.get("file") for e in entries}
    added = []
    for f in on_disk:
        if f not in known:
            entries.append({"file": f,
                            "description": _sidecar_caption(s3, ref_root(name) + f),
                            "tags": []})
            added.append(f)
    # An entry whose file is gone is FLAGGED, not dropped — losing a written
    # description because an object moved is worse than carrying a stale entry.
    # An entry with nothing written in it has nothing to preserve, so it goes:
    # otherwise every image ever moved out leaves a permanent blank behind.
    gone, dropped = [], []
    have = set(on_disk)
    kept = []
    for e in entries:
        if e.get("file") in have:
            e.pop("missing", None)
            kept.append(e)
        elif (e.get("description") or "").strip():
            e["missing"] = True
            gone.append(e["file"])
            kept.append(e)
        else:
            dropped.append(e["file"])
    entries = kept

    data["references"] = entries
    # A default_set may not name an image that is no longer there.
    if data.get("default_set"):
        data["default_set"] = [f for f in data["default_set"] if f in have]
    data.setdefault("default_set", [])
    if apply:
        write_profile(s3, name, data, etag)
    return {"added": added, "missing": gone, "dropped": dropped,
            "undescribed": [e["file"] for e in entries
                            if not (e.get("description") or "").strip()]}


# --- pools -----------------------------------------------------------------

@main.command("add-refs", epilog=(
    "\n\nArguments:\n  FILES  Local image files. Omit when using --from-run."))
@click.argument("files", nargs=-1)
@click.argument("name", required=True)
@click.option("--from-run", "from_run", multiple=True,
              help=("Promote a RUN's output into reference/ instead of a local file. "
                    "Repeatable; takes a runref like <project>/latest#1."))
@click.option("--project", help="Default project for a bare runref given to --from-run.")
@click.option("--replace", is_flag=True, help="Number from 1 (overwrites in place).")
@click.option("--start", type=int, help="Start numbering at N (default: after current highest).")
@click.option("--to", help=("Purpose subfolder inside reference/ (face, body, wardrobe, …). "
              "Omit to add at the root of reference/."))
def cmd_add_refs(files, name, from_run, project, replace, start, to):
    s3 = s3c.client()
    """Add reference image(s), optionally into a purpose subfolder.

    THIS IS THE GATE ON A CHARACTER'S IDENTITY. Everything else about a
    generation is reversible bookkeeping; what sits in `reference/` is who the
    character IS, and it is what every later render is held against. So a
    generated image never arrives here on its own — `studio character shoot`
    leaves its results in their runs and prints the `--from-run` line to promote
    the ones a person chose to keep.

    `--from-run` copies inside the bucket rather than downloading: the run keeps
    its own output, and no record ends up naming a key that moved.
    """
    check_name(name)
    if not files and not from_run:
        die("nothing to add — pass local file(s), or --from-run <runref> to promote "
            "a run's output.")
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")

    run_keys: list[str] = []
    # Keep each key paired with the shot slot its run recorded, so the spec's
    # own description and tags can be written with the image instead of being
    # retyped by hand. None for anything not shot against the spec.
    run_slots: list[str | None] = []
    for ref in from_run:
        try:
            keys = R.resolve_output_keys(s3, ref, project, kinds=IMG_EXTS)
        except R.RunError as exc:
            die(str(exc))
        run_keys += keys
        run_slots += [_run_slot(s3, ref, project)] * len(keys)

    group = to
    prefix = group_prefix(name, group)
    start = 1 if replace else (start if start is not None
                                    else pool_max_index(s3, name, "reference", group) + 1)

    folder = pool_folder(name, "reference") + (f"/{group}" if group else "")
    n = start
    for f in files:
        ext = os.path.splitext(f)[1].lower() or ".webp"
        put_file(s3, f, s3c.key(f"{folder}/{prefix}{n}{ext}"),
                 "image/webp" if ext == ".webp" else None)
        n += 1
    described: dict[str, str] = {}
    for key, slot_id in zip(run_keys, run_slots):
        ext = os.path.splitext(key)[1].lower() or ".png"
        rel = f"{group}/{prefix}{n}{ext}" if group else f"{prefix}{n}{ext}"
        dest = s3c.key(f"{folder}/{prefix}{n}{ext}")
        s3.copy_object(Bucket=s3c.BUCKET, CopySource={"Bucket": s3c.BUCKET, "Key": key},
                       Key=dest)
        print(f"  {key} -> {folder}/{prefix}{n}{ext}", file=sys.stderr)
        if slot_id:
            described[rel] = slot_id
        n += 1
    print(f"added {n - start} image(s) to {folder}/ as {prefix}{start}..{prefix}{n - 1}",
          file=sys.stderr)

    report = sync_index(s3, name)
    if described:
        _describe_from_spec(s3, name, described)
        # `report` was taken before the descriptions were written, so without
        # this the warning below names the very images just described.
        report["undescribed"] = [f for f in report["undescribed"] if f not in described]
    if report["undescribed"]:
        print(f"  {len(report['undescribed'])} reference image(s) have no description yet. "
              f"An undescribed image cannot be picked by tag and is invisible to whoever "
              f"chooses the set:\n"
              f"    studio character set-ref-desc {name} <file> "
              f"--description '…' --tags face,neutral", file=sys.stderr)


def _run_slot(s3, ref: str, project: str | None) -> str | None:
    """The shot slot a run recorded, if it was one — see `record_extra`."""
    try:
        proj, run_id = R.resolve_run(s3, ref, project)
        # `run_record` wraps the documents; the slot rides in request.json.
        record = R.run_record(s3, proj, run_id) or {}
        return ((record.get("request") or {}).get("reference_slot")) or None
    except Exception:  # noqa: BLE001 — provenance is a bonus, never a blocker
        return None


def _describe_from_spec(s3, name: str, by_file: dict[str, str]) -> None:
    """Write the shot spec's own description and tags onto promoted images.

    The spec has carried a `description` and `tags` per slot from the start, and
    for a while nothing read them: `shoot` stopped filing its output when
    promotion became a separate human gate, and `add-refs` had no idea which
    slot a run came from. So every promotion was a hand-retype of prose sitting
    in the repo — which is how the two drift apart.
    """
    from studio_pipeline.engine import shoot as SHOOT  # local: shoot imports this module
    try:
        slots = {s["id"]: s for s in SHOOT.load_spec()["slots"]}
    except Exception as exc:  # noqa: BLE001 — a broken spec must not lose the images
        print(f"  note: could not read the shot spec ({exc}); promoted images are "
              f"undescribed.", file=sys.stderr)
        return
    data, entries = read_index(s3, name)
    etag = remote_etag(s3, name)
    hits = 0
    for entry in entries:
        slot = slots.get(by_file.get(entry.get("file"), ""))
        if not slot:
            continue
        entry["description"] = " ".join(slot["description"].split())
        entry["tags"] = list(slot["tags"])
        hits += 1
    if not hits:
        return
    data["references"] = entries
    write_profile(s3, name, data, etag)
    print(f"  described {hits} image(s) from the shot spec.", file=sys.stderr)


@main.command("add-to")
@click.argument("files", nargs=-1, required=True)
@click.argument("name", required=True)
@click.argument("pool", required=True, type=click.Choice(["archive", "corpus", "seed"]))
def cmd_add_to_pool(files, name, pool):
    s3 = s3c.client()
    """Add file(s) to corpus/, seed/ or archive/ — basenames kept as they are.

    Only reference/ is numbered, because only reference/ is cited by slot.
    Renaming a source photo throws away whatever its filename recorded.
    """
    check_name(name)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")
    folder = pool_folder(name, pool)
    for f in files:
        put_file(s3, f, s3c.key(f"{folder}/{os.path.basename(f)}"))
    print(f"added {len(files)} file(s) to {folder}/", file=sys.stderr)


@main.command("sync-refs")
@click.argument("name", required=True)
@click.option("--apply", is_flag=True, help="Write the index back (default: dry run).")
def cmd_sync_refs(name, apply):
    s3 = s3c.client()
    check_name(name)
    report = sync_index(s3, name, apply=apply)
    if not apply:
        print("(dry run — pass --apply to write the index back)", file=sys.stderr)
    print(json.dumps(report, indent=2))


@main.command("set-ref-desc", epilog="\n\nArguments:\n  FILE  Path inside reference/ (e.g. face/<name>_face_3.png), or its stem.")
@click.argument("file", required=True)
@click.argument("name", required=True)
@click.option("--description")
@click.option("--tags", help="Comma-separated, replacing the existing tags.")
def cmd_set_ref_desc(file, name, description, tags):
    s3 = s3c.client()
    check_name(name)
    data, entries = read_index(s3, name)
    etag = remote_etag(s3, name)
    hit = next((e for e in entries if e.get("file") == file), None)
    if not hit:
        stems = {os.path.splitext(os.path.basename(e.get("file", "")))[0]: e for e in entries}
        hit = stems.get(file)
    if not hit:
        die(f"{name} has no reference {file!r} in its index. "
            f"Run `sync-refs {name} --apply` if it was just added.")
    if description is not None:
        hit["description"] = description
    if tags is not None:
        hit["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    data["references"] = entries
    write_profile(s3, name, data, etag)
    print(json.dumps(hit, indent=2))


@main.command("describe-refs")
@click.argument("name", required=True)
@click.option("--from-json", required=True, help="JSON object: {file: {description, tags}}.")
def cmd_describe_refs(name, from_json):
    s3 = s3c.client()
    """Describe many reference images in ONE profile write.

    Describing a 40-image library one call at a time is 40 profile round-trips
    and 40 chances to stop halfway with the index half-written. This applies a
    whole pass atomically: {file: {description, tags}}.
    """
    check_name(name)
    with open(from_json) as fh:
        batch = json.load(fh)
    if not isinstance(batch, dict):
        die("--from-json must contain an object of {file: {description, tags}}")

    data, entries = read_index(s3, name)
    etag = remote_etag(s3, name)
    by_file = {e.get("file"): e for e in entries}
    unknown = [f for f in batch if f not in by_file]
    if unknown:
        die(f"not in {name}'s reference index: {', '.join(unknown[:8])}"
            + (f" (+{len(unknown) - 8} more)" if len(unknown) > 8 else ""))

    for f, spec in batch.items():
        if "description" in spec:
            by_file[f]["description"] = spec["description"]
        if "tags" in spec:
            by_file[f]["tags"] = list(spec["tags"])
    data["references"] = entries
    write_profile(s3, name, data, etag)
    left = [e["file"] for e in entries if not (e.get("description") or "").strip()]
    print(f"described {len(batch)} image(s); {len(left)} still undescribed", file=sys.stderr)
    if left:
        print("\n".join(left))


@main.command("default-set")
@click.argument("name", required=True)
@click.option("--set", "set_", multiple=True, help="Files from the index, in slot order. Repeat the flag per file.")
def cmd_default_set(name, set_):
    s3 = s3c.client()
    """Name the images sent when --character is given with no selector."""
    check_name(name)
    data, entries = read_index(s3, name)
    etag = remote_etag(s3, name)
    if set_ is None:
        print(json.dumps(data.get("default_set") or [], indent=2))
        return
    known = {e.get("file") for e in entries}
    unknown = [f for f in set_ if f not in known]
    if unknown:
        die(f"not in {name}'s reference index: {', '.join(unknown)}")
    data["default_set"] = list(set_)
    write_profile(s3, name, data, etag)
    print(json.dumps(data["default_set"], indent=2))


@main.command("pool")
@click.argument("name", required=True)
@click.argument("pool", required=True, type=click.Choice(["archive", "corpus", "seed"]))
@click.option("--expires", type=int, default=3600)
@click.option("--json", "json_", is_flag=True)
@click.option("--presign", is_flag=True)
def cmd_pool(name, pool, expires, json_, presign):
    s3 = s3c.client()
    """List a non-reference pool. These are material, not identity."""
    check_name(name)
    keys = s3c.list_keys(s3, pool_folder(name, pool))
    if not keys:
        print(f"({name} has nothing in {pool}/)", file=sys.stderr)
        return
    if presign:
        urls = [s3.generate_presigned_url("get_object",
                                          Params={"Bucket": s3c.BUCKET, "Key": k},
                                          ExpiresIn=expires) for k in keys]
        print(json.dumps(urls, indent=2) if json_ else "\n".join(urls))
    elif json_:
        print(json.dumps(keys, indent=2))
    else:
        print("\n".join(keys))
    if pool == "archive":
        print("note: archive/ is retired material — do not feed it to a model unless "
              "the user asked for these specifically.", file=sys.stderr)


@main.command("refs")
@click.argument("name", required=True)
@click.option("--describe", is_flag=True, help="Print the indexed description of every reference image.")
@click.option("--dest", help="Local dir for a download (default: a fresh temp dir).")
@click.option("--expires", type=int, default=3600, help="Presign expiry seconds (default 3600).")
@click.option("--json", "json_", is_flag=True, help="JSON output.")
@click.option("--keys", is_flag=True, help="Print S3 keys instead of downloading.")
@click.option("--pick", help="Comma-separated files (or bare stems) from the index.")
@click.option("--pick-tag", help="Comma-separated tags; an image must carry ALL of them.")
@click.option("--presign", is_flag=True, help="Print ordered presigned HTTPS URLs.")
@click.option("--slots", help=("Comma-separated 1-based positions WITHIN the resolved "
              "selection."))
def cmd_refs(name, describe, dest, expires, json_, keys, pick, pick_tag, presign, slots):
    s3 = s3c.client()
    """The reference set: describe it, or resolve a selection of it."""
    check_name(name)

    if describe:
        _data, entries = read_index(s3, name)
        if not entries:
            die(f"{name} has no reference index. Build one with "
                f"`studio character sync-refs {name} --apply`.")
        if json_:
            print(json.dumps(entries, indent=2))
        else:
            for e in entries:
                tags = ",".join(e.get("tags") or []) or "-"
                flag = " [MISSING]" if e.get("missing") else ""
                print(f"{e.get('file'):<40} {tags:<24} "
                      f"{e.get('description') or '(no description)'}{flag}")
        return

    pick = [x.strip() for x in pick.split(",")] if pick else None
    tags = [t.strip() for t in pick_tag.split(",")] if pick_tag else None
    slots = [int(x) for x in slots.split(",")] if slots else None
    keys = resolve_selection(s3, name, pick, tags, slots)
    if not keys:
        die(f"no reference images resolved for {name}")

    if presign:
        results = [{"key": k,
                    "url": s3.generate_presigned_url(
                        "get_object", Params={"Bucket": s3c.BUCKET, "Key": k},
                        ExpiresIn=expires)} for k in keys]
        if json_:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(r["url"])
        print(f"presigned {len(keys)} reference image(s) for {name} ({expires}s). "
              "Slot N is position N in THIS list; cite as [Image1]…", file=sys.stderr)
        return

    if keys:
        print(json.dumps(keys, indent=2) if json_ else "\n".join(keys))
        return

    dest = dest or tempfile.mkdtemp(prefix=f"{name}-refs-")
    os.makedirs(dest, exist_ok=True)
    out: dict[str, str] = {}
    for k in keys:
        base = os.path.basename(k)
        local = os.path.join(dest, base)
        s3.download_file(s3c.BUCKET, k, local)
        out[base] = os.path.abspath(local)
    print(json.dumps(out, indent=2))
    print(f"downloaded {len(out)} reference image(s) to {dest}. For Replicate prefer "
          "`refs <name> --presign` (full-res, zero context cost).", file=sys.stderr)




