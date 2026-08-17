# /// script
# requires-python = ">=3.13"
# dependencies = ["boto3", "pyyaml"]
# ///
"""character.py — manage on-model characters stored in the
xharness-prod-media-us-east-1 S3 bucket.

A character is DATA, not a skill: each one is an S3 record under
`characters/<name>/` (see the `s3` skill), and this one tool manages them all:

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

Requires an AWS login (`aws login`; see the `s3` skill).

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
  uv run .../character.py create <name> --from-profile /tmp/<name>.yaml
  uv run .../character.py add-refs <name> --to face /tmp/*.png
  uv run .../character.py refs <name> --describe
  uv run .../character.py refs <name> --pick-tag face --presign --json
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import tempfile

import yaml

# Reuse the s3 skill's shared helpers (one storage layer, one auth bridge).
_S3_SCRIPTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "s3", "scripts"
)
sys.path.insert(0, os.path.abspath(_S3_SCRIPTS))
try:
    import paths as P  # noqa: E402
    import s3_common as s3c  # noqa: E402
except ImportError:  # pragma: no cover
    print(
        "error: cannot import the s3 skill's s3_common.py — the `s3` skill must be "
        f"present at {os.path.abspath(_S3_SCRIPTS)}.",
        file=sys.stderr,
    )
    sys.exit(1)

PROFILE_FILE = "profile.yaml"
PROFILE_CT = "application/yaml"
TEMPLATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "templates", PROFILE_FILE
)
# Working copies for `edit` live in the repo (git-ignored) so they are easy to
# open in an editor: <repo>/local/characters/<name>.yaml
LOCAL_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "local", "characters"
    )
)
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

def cmd_list(args, s3) -> None:
    names = P.list_characters(s3)
    if args.json:
        print(json.dumps(names, indent=2))
    elif names:
        print("\n".join(names))
    else:
        print("(no characters yet — create one with `character.py create <name>`)", file=sys.stderr)


def cmd_show(args, s3) -> None:
    check_name(args.name)
    key = profile_key(args.name)
    try:
        body = s3.get_object(Bucket=s3c.BUCKET, Key=key)["Body"].read()
    except s3.exceptions.NoSuchKey:
        die(f"no {PROFILE_FILE} for character {args.name!r} (looked at s3://{s3c.BUCKET}/{key}).")
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


def cmd_textblock(args, s3) -> None:
    """Emit a pasteable text identity block for engines with no reference system.

    Seedance and Kling-on-Replicate both carry identity through `reference_images`;
    when driving from a start frame instead, the character has to survive as
    PROSE in the prompt. If the bible has an authored `text_identity_block` that
    is the canonical answer and is printed verbatim. Otherwise this prints the
    identity-bearing keys as raw material to compress — the script can't write
    prose.
    """
    check_name(args.name)
    data = load_profile(s3, args.name)

    authored = (data.get("text_identity_block") or "").strip()
    if authored and not authored.startswith("<"):  # "<>" is the unfilled template
        print(authored)
        print(f"\n(authored block from {args.name}'s bible)", file=sys.stderr)
        return

    raw = {k: data[k] for k in TEXTBLOCK_KEYS if data.get(k)}
    sys.stdout.write(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=88))

    print(
        f"\nNo authored `text_identity_block` in {args.name}'s bible — the above is raw "
        "material.\nCompress it into ONE paragraph of ~50-70 words covering only what a "
        "text-only engine\ncannot infer: build proportion, hair, face landmarks, skin, and "
        "signature accessories.\nThen save it back into the bible under `text_identity_block:` "
        f"(`character.py edit {args.name}`)\nso it is written once and reused.\n"
        "\nNOTE: with a start frame supplied, keep the pasted block SHORT — the frame carries\n"
        "appearance better than prose, and a long block fights it (see studio-kling).",
        file=sys.stderr,
    )


def cmd_create(args, s3) -> None:
    check_name(args.name)
    src = args.from_profile or TEMPLATE
    if not os.path.isfile(src):
        die(f"profile source not found: {src}")
    if src != TEMPLATE:  # the template is deliberately unfilled; anything else must be real
        check_profile(parse_profile(read_text(src), src), src, args.name)
    uri = put_file(s3, src, profile_key(args.name), PROFILE_CT)
    print(f"created character {args.name!r}: {uri}", file=sys.stderr)
    if src == TEMPLATE:
        print("  (blank template — fill it in, then `set-profile` the result.)", file=sys.stderr)
    print(f"  next: add references with `character.py add-refs {args.name} <img>...`", file=sys.stderr)


def cmd_set_profile(args, s3) -> None:
    check_name(args.name)
    if not os.path.isfile(args.file):
        die(f"profile file not found: {args.file}")
    check_profile(parse_profile(read_text(args.file), args.file), args.file, args.name)
    uri = put_file(s3, args.file, profile_key(args.name), PROFILE_CT)
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
    except Exception:  # noqa: BLE001 — absent or unreadable; caller treats as unknown
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


def do_pull(s3, args, local: str, base: str, etagf: str) -> None:
    text, etag = fetch_profile(s3, args.name)
    if os.path.exists(local) and not args.force:
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
        f"pulled s3://{s3c.BUCKET}/{profile_key(args.name)}\n"
        f"  edit the file above, then re-run `edit {args.name}` to upload it.",
        file=sys.stderr,
    )


def do_push(s3, args, local: str, base: str, etagf: str) -> None:
    if not os.path.isfile(local):
        die(f"no local copy at {local} — run `edit {args.name}` first to pull it.")
    text = read_text(local)
    prior = read_text(base) if os.path.exists(base) else None

    if prior is None and not args.force:
        die(
            f"no pull record for {local} (missing {os.path.basename(base)}), so edits made\n"
            "  elsewhere cannot be detected. Re-run with --force to upload anyway."
        )
    if prior is not None and text == prior:
        print(f"no local changes in {local} — nothing to upload.", file=sys.stderr)
        return

    recorded = read_text(etagf).strip() if os.path.exists(etagf) else None
    current = remote_etag(s3, args.name)
    if recorded and current and recorded != current and not args.force:
        die(
            f"s3 {PROFILE_FILE} for {args.name!r} changed since you pulled it — uploading would\n"
            "  discard that change. Re-run with --force to overwrite, or --discard to\n"
            "  throw away your local edits and re-pull."
        )

    # A bible that no longer parses, or has lost a schema key, is worse than no
    # upload at all — every downstream reader breaks on it. Check before the PUT.
    check_profile(parse_profile(text, local), local, args.name)

    if prior is not None:
        sys.stderr.write(unified(prior, text, args.name))
    uri = put_file(s3, local, f"{args.name}/{PROFILE_FILE}", PROFILE_CT)
    write_text(base, text)
    write_text(etagf, remote_etag(s3, args.name) or "")
    print(f"uploaded {uri}", file=sys.stderr)


def cmd_edit(args, s3) -> None:
    check_name(args.name)
    local, base, etagf = local_paths(args.name, args.path)

    if args.discard:
        args.force = True
        do_pull(s3, args, local, base, etagf)
        return

    if args.diff:
        if not os.path.isfile(local):
            die(f"no local copy at {local} — run `edit {args.name}` first to pull it.")
        remote, _ = fetch_profile(s3, args.name)
        diff = unified(remote, read_text(local), args.name)
        sys.stdout.write(diff if diff else "")
        if not diff:
            print(f"{local} matches s3.", file=sys.stderr)
        return

    # Direction: explicit flags win; otherwise pull when there is no working copy
    # yet, push once there is one. That makes the flow "run, edit, run again".
    if args.pull:
        do_pull(s3, args, local, base, etagf)
    elif args.push or os.path.isfile(local):
        do_push(s3, args, local, base, etagf)
    else:
        do_pull(s3, args, local, base, etagf)


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
    except Exception:  # noqa: BLE001
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
                die(f"{name} has no reference {want!r}. See `character.py refs {name} --describe`.")
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

def cmd_add_refs(args, s3) -> None:
    """Add reference image(s), optionally into a purpose subfolder."""
    check_name(args.name)
    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")
    group = args.to
    prefix = group_prefix(args.name, group)
    start = 1 if args.replace else (args.start if args.start is not None
                                    else pool_max_index(s3, args.name, "reference", group) + 1)

    folder = pool_folder(args.name, "reference") + (f"/{group}" if group else "")
    for i, f in enumerate(args.files):
        n = start + i
        ext = os.path.splitext(f)[1].lower() or ".webp"
        put_file(s3, f, s3c.key(f"{folder}/{prefix}{n}{ext}"),
                 "image/webp" if ext == ".webp" else None)
    last = start + len(args.files) - 1
    print(f"added {len(args.files)} image(s) to {folder}/ as {prefix}{start}..{prefix}{last}",
          file=sys.stderr)

    report = sync_index(s3, args.name)
    if report["undescribed"]:
        print(f"  {len(report['undescribed'])} reference image(s) have no description yet. "
              f"An undescribed image cannot be picked by tag and is invisible to whoever "
              f"chooses the set:\n"
              f"    character.py set-ref-desc {args.name} <file> "
              f"--description '…' --tags face,neutral", file=sys.stderr)


def cmd_add_to_pool(args, s3) -> None:
    """Add file(s) to corpus/, seed/ or archive/ — basenames kept as they are.

    Only reference/ is numbered, because only reference/ is cited by slot.
    Renaming a source photo throws away whatever its filename recorded.
    """
    check_name(args.name)
    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        die(f"file(s) not found: {', '.join(missing)}")
    folder = pool_folder(args.name, args.pool)
    for f in args.files:
        put_file(s3, f, s3c.key(f"{folder}/{os.path.basename(f)}"))
    print(f"added {len(args.files)} file(s) to {folder}/", file=sys.stderr)


def cmd_sync_refs(args, s3) -> None:
    check_name(args.name)
    report = sync_index(s3, args.name, apply=args.apply)
    if not args.apply:
        print("(dry run — pass --apply to write the index back)", file=sys.stderr)
    print(json.dumps(report, indent=2))


def cmd_set_ref_desc(args, s3) -> None:
    check_name(args.name)
    data, entries = read_index(s3, args.name)
    etag = remote_etag(s3, args.name)
    hit = next((e for e in entries if e.get("file") == args.file), None)
    if not hit:
        stems = {os.path.splitext(os.path.basename(e.get("file", "")))[0]: e for e in entries}
        hit = stems.get(args.file)
    if not hit:
        die(f"{args.name} has no reference {args.file!r} in its index. "
            f"Run `sync-refs {args.name} --apply` if it was just added.")
    if args.description is not None:
        hit["description"] = args.description
    if args.tags is not None:
        hit["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    data["references"] = entries
    write_profile(s3, args.name, data, etag)
    print(json.dumps(hit, indent=2))


def cmd_describe_refs(args, s3) -> None:
    """Describe many reference images in ONE profile write.

    Describing a 40-image library one call at a time is 40 profile round-trips
    and 40 chances to stop halfway with the index half-written. This applies a
    whole pass atomically: {file: {description, tags}}.
    """
    check_name(args.name)
    with open(args.from_json) as fh:
        batch = json.load(fh)
    if not isinstance(batch, dict):
        die("--from-json must contain an object of {file: {description, tags}}")

    data, entries = read_index(s3, args.name)
    etag = remote_etag(s3, args.name)
    by_file = {e.get("file"): e for e in entries}
    unknown = [f for f in batch if f not in by_file]
    if unknown:
        die(f"not in {args.name}'s reference index: {', '.join(unknown[:8])}"
            + (f" (+{len(unknown) - 8} more)" if len(unknown) > 8 else ""))

    for f, spec in batch.items():
        if "description" in spec:
            by_file[f]["description"] = spec["description"]
        if "tags" in spec:
            by_file[f]["tags"] = list(spec["tags"])
    data["references"] = entries
    write_profile(s3, args.name, data, etag)
    left = [e["file"] for e in entries if not (e.get("description") or "").strip()]
    print(f"described {len(batch)} image(s); {len(left)} still undescribed", file=sys.stderr)
    if left:
        print("\n".join(left))


def cmd_default_set(args, s3) -> None:
    """Name the images sent when --character is given with no selector."""
    check_name(args.name)
    data, entries = read_index(s3, args.name)
    etag = remote_etag(s3, args.name)
    if args.set is None:
        print(json.dumps(data.get("default_set") or [], indent=2))
        return
    known = {e.get("file") for e in entries}
    unknown = [f for f in args.set if f not in known]
    if unknown:
        die(f"not in {args.name}'s reference index: {', '.join(unknown)}")
    data["default_set"] = list(args.set)
    write_profile(s3, args.name, data, etag)
    print(json.dumps(data["default_set"], indent=2))


def cmd_pool(args, s3) -> None:
    """List a non-reference pool. These are material, not identity."""
    check_name(args.name)
    keys = s3c.list_keys(s3, pool_folder(args.name, args.pool))
    if not keys:
        print(f"({args.name} has nothing in {args.pool}/)", file=sys.stderr)
        return
    if args.presign:
        urls = [s3.generate_presigned_url("get_object",
                                          Params={"Bucket": s3c.BUCKET, "Key": k},
                                          ExpiresIn=args.expires) for k in keys]
        print(json.dumps(urls, indent=2) if args.json else "\n".join(urls))
    elif args.json:
        print(json.dumps(keys, indent=2))
    else:
        print("\n".join(keys))
    if args.pool == "archive":
        print("note: archive/ is retired material — do not feed it to a model unless "
              "the user asked for these specifically.", file=sys.stderr)


def cmd_refs(args, s3) -> None:
    """The reference set: describe it, or resolve a selection of it."""
    check_name(args.name)

    if args.describe:
        _data, entries = read_index(s3, args.name)
        if not entries:
            die(f"{args.name} has no reference index. Build one with "
                f"`character.py sync-refs {args.name} --apply`.")
        if args.json:
            print(json.dumps(entries, indent=2))
        else:
            for e in entries:
                tags = ",".join(e.get("tags") or []) or "-"
                flag = " [MISSING]" if e.get("missing") else ""
                print(f"{e.get('file'):<40} {tags:<24} "
                      f"{e.get('description') or '(no description)'}{flag}")
        return

    pick = [x.strip() for x in args.pick.split(",")] if args.pick else None
    tags = [t.strip() for t in args.pick_tag.split(",")] if args.pick_tag else None
    slots = [int(x) for x in args.slots.split(",")] if args.slots else None
    keys = resolve_selection(s3, args.name, pick, tags, slots)
    if not keys:
        die(f"no reference images resolved for {args.name}")

    if args.presign:
        results = [{"key": k,
                    "url": s3.generate_presigned_url(
                        "get_object", Params={"Bucket": s3c.BUCKET, "Key": k},
                        ExpiresIn=args.expires)} for k in keys]
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(r["url"])
        print(f"presigned {len(keys)} reference image(s) for {args.name} ({args.expires}s). "
              "Slot N is position N in THIS list; cite as [Image1]…", file=sys.stderr)
        return

    if args.keys:
        print(json.dumps(keys, indent=2) if args.json else "\n".join(keys))
        return

    dest = args.dest or tempfile.mkdtemp(prefix=f"{args.name}-refs-")
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


def main() -> int:
    p = argparse.ArgumentParser(
        description="Manage on-model characters stored in S3 (characters/<name>/).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="List every character.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="Print a character's profile.yaml.")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser(
        "textblock",
        help="Emit a pasteable text identity block, for when no reference set is used.",
    )
    sp.add_argument("name")
    sp.set_defaults(func=cmd_textblock)

    sp = sub.add_parser("create", help="Create a character record (uploads a profile.yaml).")
    sp.add_argument("name")
    sp.add_argument("--from-profile", help="Local profile.yaml to seed with (default: blank template).")
    sp.set_defaults(func=cmd_create)

    sp = sub.add_parser("set-profile", help="Replace a character's profile.yaml.")
    sp.add_argument("name")
    sp.add_argument("file")
    sp.set_defaults(func=cmd_set_profile)

    sp = sub.add_parser(
        "edit",
        help="Round-trip profile.yaml for local editing (first run pulls, next run pushes).",
    )
    sp.add_argument("name")
    sp.add_argument("--path", help=f"Working-copy path (default: {os.path.join(LOCAL_DIR, '<name>.yaml')}).")
    sp.add_argument("--pull", action="store_true", help="Force the download direction.")
    sp.add_argument("--push", action="store_true", help="Force the upload direction.")
    sp.add_argument("--diff", action="store_true", help="Show local-vs-S3 differences and exit.")
    sp.add_argument("--discard", action="store_true", help="Throw away local edits and re-pull.")
    sp.add_argument("--force", action="store_true", help="Proceed despite unsaved edits or a changed remote.")
    sp.set_defaults(func=cmd_edit)

    sp = sub.add_parser("add-refs", help="Add reference image(s), numbered within their group.")
    sp.add_argument("name")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--to", metavar="GROUP",
                    help="Purpose subfolder inside reference/ (face, body, wardrobe, …). "
                         "Omit to add at the root of reference/.")
    sp.add_argument("--start", type=int, help="Start numbering at N (default: after current highest).")
    sp.add_argument("--replace", action="store_true", help="Number from 1 (overwrites in place).")
    sp.set_defaults(func=cmd_add_refs)

    sp = sub.add_parser("refs", help="The reference set: describe it, or resolve a selection.")
    sp.add_argument("name")
    sp.add_argument("--describe", action="store_true",
                    help="Print the indexed description of every reference image.")
    sp.add_argument("--pick", help="Comma-separated files (or bare stems) from the index.")
    sp.add_argument("--pick-tag", help="Comma-separated tags; an image must carry ALL of them.")
    sp.add_argument("--slots", help="Comma-separated 1-based positions WITHIN the resolved selection.")
    sp.add_argument("--keys", action="store_true", help="Print S3 keys instead of downloading.")
    sp.add_argument("--dest", help="Local dir for a download (default: a fresh temp dir).")
    sp.add_argument("--presign", action="store_true", help="Print ordered presigned HTTPS URLs.")
    sp.add_argument("--expires", type=int, default=3600, help="Presign expiry seconds (default 3600).")
    sp.add_argument("--json", action="store_true", help="JSON output.")
    sp.set_defaults(func=cmd_refs)

    sp = sub.add_parser("sync-refs",
                        help="Reconcile the bible's reference index against reference/.")
    sp.add_argument("name")
    sp.add_argument("--apply", action="store_true", help="Write the index back (default: dry run).")
    sp.set_defaults(func=cmd_sync_refs)

    sp = sub.add_parser("set-ref-desc", help="Describe and tag one reference image.")
    sp.add_argument("name")
    sp.add_argument("file", help="Path inside reference/ (e.g. face/<name>_face_3.png), or its stem.")
    sp.add_argument("--description")
    sp.add_argument("--tags", help="Comma-separated, replacing the existing tags.")
    sp.set_defaults(func=cmd_set_ref_desc)

    sp = sub.add_parser("describe-refs",
                        help="Describe many reference images in one profile write.")
    sp.add_argument("name")
    sp.add_argument("--from-json", required=True,
                    help="JSON object: {file: {description, tags}}.")
    sp.set_defaults(func=cmd_describe_refs)

    sp = sub.add_parser("default-set",
                        help="The images sent when --character is given with no selector.")
    sp.add_argument("name")
    sp.add_argument("--set", nargs="+", help="Files from the index, in slot order.")
    sp.set_defaults(func=cmd_default_set)

    sp = sub.add_parser("add-to", help="Add file(s) to corpus/, seed/ or archive/.")
    sp.add_argument("name")
    sp.add_argument("pool", choices=[p for p in P.CHAR_POOLS if p != "reference"])
    sp.add_argument("files", nargs="+")
    sp.set_defaults(func=cmd_add_to_pool)

    sp = sub.add_parser("pool", help="List corpus/, seed/ or archive/.")
    sp.add_argument("name")
    sp.add_argument("pool", choices=[p for p in P.CHAR_POOLS if p != "reference"])
    sp.add_argument("--presign", action="store_true")
    sp.add_argument("--expires", type=int, default=3600)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_pool)

    args = p.parse_args()
    s3 = s3c.client()
    args.func(args, s3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
