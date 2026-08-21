"""The described reference index, and the commands that maintain it.

`reference/` holds far more images than any engine accepts (Kling 7, Seedance 9,
Nano Banana 14), so something has to say WHICH ones to send. That something is
the bible: `references:` describes every image, `default_set:` names the ones
sent when nobody picks, and `resolve_selection` turns a `--pick` / `--pick-tag`
/ default into an ordered list of keys.

**Slot N is position N in the resolved selection**, not a trailing file number.
With subfolders a filename number is unique only within its group, so the
position a model sees is the only stable citation.

Every write goes through `profile.write_profile`, which refuses on a changed
ETag — so a description written while someone else was editing the bible fails
instead of quietly dropping their edit.
"""
from __future__ import annotations

import json
import mimetypes
import os
import pathlib
import sys
import tempfile

import click

from studio_pipeline.adapters import api, store
# For `add-refs --from-run`: resolving a runref to its output keys. One-way —
# the run store knows nothing about characters.
from studio_pipeline.domain import runs as R
from studio_pipeline.domain.characters.base import (
    IMG_EXTS,
    check_name,
    die,
    group_prefix,
    pool_folder,
    pool_max_index,
    put_file,
)
from studio_pipeline.domain.characters.profile import (
    load_profile,
    remote_version,
    write_profile,
)

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

def ref_root(name: str) -> str:
    return pool_folder(name, "reference") + "/"


def ref_files(name: str) -> list[str]:
    """Every image in reference/, as paths relative to it. Sidecars excluded.

    **Recursive, and it has to be**, which is the one place `store.files` is not
    enough on its own: the index keys entries on `face/<name>_1.png`, so a
    listing one folder deep would see the group folders and none of the images
    inside them, and `sync_index` would then drop every described entry as
    missing. `list_keys` was recursive by default and hid this; walking is now
    explicit.
    """
    root = ref_root(name)
    found = []

    def walk(prefix: str) -> None:
        for entry in store.children_or_empty(prefix):
            path = f"{prefix}/{entry['name']}"
            if entry.get("kind") == "folder":
                walk(path)
            elif os.path.splitext(entry["name"])[1].lower() in IMG_EXTS:
                found.append(path[len(root):])

    walk(root.rstrip("/"))
    return sorted(found, key=store.natural_key)


def _sidecar_caption(image_key: str) -> str:
    """Text of the <basename>.txt sidecar next to an image key, or '' if none.

    Predates the profile index. Kept as a fallback so a character whose
    descriptions were only ever written as sidecars still reads sensibly.
    """
    try:
        return store.read(os.path.splitext(image_key)[0] + ".txt").decode("utf-8").strip()
    except api.NotFound:
        return ""


def read_index(name: str) -> tuple[dict, list[dict]]:
    """(profile, references) — the index as the bible currently records it."""
    data = load_profile(name)
    entries = data.get("references") or []
    if not isinstance(entries, list):
        die(f"{name}'s `references:` must be a list of {{file, description, tags}} entries")
    return data, entries


def resolve_selection(name: str, pick: list[str] | None = None,
                      tags: list[str] | None = None,
                      slots: list[int] | None = None) -> list[str]:
    """Which reference images to send, as S3 keys, in index order.

    Resolution order: --pick names > --pick-tag > default_set > everything.
    The last of those is a fallback, not a default worth relying on: a character
    with a large reference/ and no default_set will overrun every model's cap,
    and the caller is expected to say so rather than truncate.
    """
    _data, entries = read_index(name)
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
        data, _ = read_index(name)
        chosen = list(data.get("default_set") or []) or [e["file"] for e in entries]
        if not chosen:
            chosen = ref_files(name)

    keys = [root + f for f in chosen]
    if slots:
        try:
            keys = [keys[i - 1] for i in slots]
        except IndexError:
            die(f"--slots out of range: the selection has {len(keys)} image(s)")
    return keys


def sync_index(name: str, *, rename_map: dict[str, str] | None = None,
               apply: bool = True) -> dict:
    """Reconcile `references:` against what is actually in reference/.

    Renames are FOLLOWED rather than re-derived, so a description stays with its
    image when curate.py renumbers or moves one. A file that has vanished is
    marked `missing: true` rather than dropped — losing a written description
    because an object moved is worse than carrying a stale entry.
    """
    data, entries = read_index(name)
    version = remote_version(name)
    for e in entries:
        if rename_map and e.get("file") in rename_map:
            e["file"] = rename_map[e["file"]]

    on_disk = ref_files(name)
    known = {e.get("file") for e in entries}
    added = []
    for f in on_disk:
        if f not in known:
            entries.append({"file": f,
                            "description": _sidecar_caption(ref_root(name) + f),
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
        write_profile(name, data, version)
    return {"added": added, "missing": gone, "dropped": dropped,
            "undescribed": [e["file"] for e in entries
                            if not (e.get("description") or "").strip()]}


# --- writing into the index ------------------------------------------------

@click.command("add-refs", epilog=(
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
            keys = R.resolve_output_keys(ref, project, kinds=IMG_EXTS)
        except R.RunError as exc:
            die(str(exc))
        run_keys += keys
        run_slots += [_run_slot(ref, project)] * len(keys)

    group = to
    prefix = group_prefix(name, group)
    start = 1 if replace else (start if start is not None
                                    else pool_max_index(name, "reference", group) + 1)

    folder = pool_folder(name, "reference") + (f"/{group}" if group else "")
    store.folder(folder)
    n = start
    for f in files:
        ext = os.path.splitext(f)[1].lower() or ".webp"
        put_file(f, f"{folder}/{prefix}{n}{ext}",
                 "image/webp" if ext == ".webp" else None)
        n += 1
    described: dict[str, str] = {}
    for key, slot_id in zip(run_keys, run_slots):
        ext = os.path.splitext(key)[1].lower() or ".png"
        rel = f"{group}/{prefix}{n}{ext}" if group else f"{prefix}{n}{ext}"
        dest = f"{folder}/{prefix}{n}{ext}"
        # A read plus a write where this was a server-side `CopyObject`. The run
        # keeps its own output — that is the point of promoting rather than
        # moving — so two blobs is the correct outcome here and not merely the
        # affordable one. See `store.copy`.
        store.copy(key, dest, content_type=mimetypes.guess_type(dest)[0]
                   or "application/octet-stream")
        print(f"  {key} -> {folder}/{prefix}{n}{ext}", file=sys.stderr)
        if slot_id:
            described[rel] = slot_id
        n += 1
    print(f"added {n - start} image(s) to {folder}/ as {prefix}{start}..{prefix}{n - 1}",
          file=sys.stderr)

    report = sync_index(name)
    if described:
        _describe_from_spec(name, described)
        # `report` was taken before the descriptions were written, so without
        # this the warning below names the very images just described.
        report["undescribed"] = [f for f in report["undescribed"] if f not in described]
    if report["undescribed"]:
        print(f"  {len(report['undescribed'])} reference image(s) have no description yet. "
              f"An undescribed image cannot be picked by tag and is invisible to whoever "
              f"chooses the set:\n"
              f"    studio character set-ref-desc {name} <file> "
              f"--description '…' --tags face,neutral", file=sys.stderr)


def _run_slot(ref: str, project: str | None) -> str | None:
    """The shot slot a run recorded, if it was one — see `record_extra`."""
    try:
        proj, run_id = R.resolve_run(ref, project)
        # `run_record` wraps the documents; the slot rides in request.json.
        record = R.run_record(proj, run_id) or {}
        return ((record.get("request") or {}).get("reference_slot")) or None
    except Exception:  # noqa: BLE001 — provenance is a bonus, never a blocker
        return None


def _describe_from_spec(name: str, by_file: dict[str, str]) -> None:
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
    data, entries = read_index(name)
    version = remote_version(name)
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
    write_profile(name, data, version)
    print(f"  described {hits} image(s) from the shot spec.", file=sys.stderr)


@click.command("sync-refs")
@click.argument("name", required=True)
@click.option("--apply", is_flag=True, help="Write the index back (default: dry run).")
def cmd_sync_refs(name, apply):
    check_name(name)
    report = sync_index(name, apply=apply)
    if not apply:
        print("(dry run — pass --apply to write the index back)", file=sys.stderr)
    print(json.dumps(report, indent=2))


@click.command("set-ref-desc", epilog="\n\nArguments:\n  FILE  Path inside reference/ (e.g. face/<name>_face_3.png), or its stem.")
@click.argument("file", required=True)
@click.argument("name", required=True)
@click.option("--description")
@click.option("--tags", help="Comma-separated, replacing the existing tags.")
def cmd_set_ref_desc(file, name, description, tags):
    check_name(name)
    data, entries = read_index(name)
    version = remote_version(name)
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
    write_profile(name, data, version)
    print(json.dumps(hit, indent=2))


@click.command("describe-refs")
@click.argument("name", required=True)
@click.option("--from-json", required=True, help="JSON object: {file: {description, tags}}.")
def cmd_describe_refs(name, from_json):
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

    data, entries = read_index(name)
    version = remote_version(name)
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
    write_profile(name, data, version)
    left = [e["file"] for e in entries if not (e.get("description") or "").strip()]
    print(f"described {len(batch)} image(s); {len(left)} still undescribed", file=sys.stderr)
    if left:
        print("\n".join(left))


@click.command("default-set")
@click.argument("name", required=True)
@click.option("--set", "set_", multiple=True, help="Files from the index, in slot order. Repeat the flag per file.")
def cmd_default_set(name, set_):
    """Name the images sent when --character is given with no selector."""
    check_name(name)
    data, entries = read_index(name)
    version = remote_version(name)
    if set_ is None:
        print(json.dumps(data.get("default_set") or [], indent=2))
        return
    known = {e.get("file") for e in entries}
    unknown = [f for f in set_ if f not in known]
    if unknown:
        die(f"not in {name}'s reference index: {', '.join(unknown)}")
    data["default_set"] = list(set_)
    write_profile(name, data, version)
    print(json.dumps(data["default_set"], indent=2))


@click.command("refs")
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
    _warn_ignored_expiry(expires)
    """The reference set: describe it, or resolve a selection of it."""
    check_name(name)

    if describe:
        _data, entries = read_index(name)
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
    # `selected`, not `keys`. `keys` is the `--keys` FLAG, and this line used to
    # overwrite it with the resolved list — so `if keys:` below tested the list
    # rather than the flag and was true whenever the character had any
    # references at all. `studio character refs <name>` has therefore always
    # printed keys and never downloaded anything, in flat contradiction of
    # `--keys`' own help ("Print S3 keys instead of downloading"), and the
    # download branch under it was unreachable code. Found by splitting this
    # module: ruff saw `tempfile` used and unimported, which it could only be
    # because nothing ever ran the line. Renaming the flag's parameter is not
    # available — `cli_surface_reference.json` records the dest.
    selected = resolve_selection(name, pick, tags, slots)
    if not selected:
        die(f"no reference images resolved for {name}")

    if presign:
        results = [{"key": k, "url": store.presign(k)} for k in selected]
        if json_:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(r["url"])
        print(f"presigned {len(selected)} reference image(s) for {name}. "
              "Slot N is position N in THIS list; cite as [Image1]…", file=sys.stderr)
        return

    if keys:
        print(json.dumps(selected, indent=2) if json_ else "\n".join(selected))
        return

    dest = dest or tempfile.mkdtemp(prefix=f"{name}-refs-")
    os.makedirs(dest, exist_ok=True)
    out: dict[str, str] = {}
    for k in selected:
        base = os.path.basename(k)
        local = os.path.join(dest, base)
        store.download(k, pathlib.Path(local))
        out[base] = os.path.abspath(local)
    print(json.dumps(out, indent=2))
    print(f"downloaded {len(out)} reference image(s) to {dest}. For Replicate prefer "
          "`refs <name> --presign` (full-res, zero context cost).", file=sys.stderr)




def _warn_ignored_expiry(expires: int) -> None:
    """`--expires` is accepted and ignored, loudly. See `objects/presign.py`."""
    context = click.get_current_context(silent=True)
    if context is None:
        return
    source = context.get_parameter_source("expires")
    if source is not None and source.name != "DEFAULT":
        click.echo(
            f"warning: --expires {expires} is ignored; the API sets the URL's lifetime.",
            err=True,
        )
