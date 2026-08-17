"""`studio migrate-layout` — move the bucket from the old tree to the new one.

    OLD                                   NEW
    media/<owner>/profile.yaml            characters/<owner>/profile.yaml
    media/<owner>/reference/…             characters/<owner>/reference/…
    media/<owner>/input/<o>_in_N.png      characters/<owner>/reference/…   (generated)
    media/<owner>/input/…                 characters/<owner>/corpus/…      (raw uploads)
    media/<owner>/originals/…             characters/<owner>/seed/…
    media/<owner>/other/…                 characters/<owner>/corpus/…
    media/<owner>/trash/…                 characters/<owner>/archive/…
    media/<owner>/favorites/…             projects/<owner>/favorites/…
    media/<owner>/runs/…                  projects/<owner>/runs/…
    media/<owner>/scenes/<id>/parts/…     projects/<owner>/scenes/<id>/shots/shot-NN.…
    media/<owner>/chains/…                projects/<owner>/chains/…
    media/phrasebook/…                    phrasebook/…

The map itself lives in `paths.classify()`, so the code that moves keys and the
code that builds them agree by construction.

FIVE PHASES, EACH ITS OWN INVOCATION
------------------------------------
    plan     what would move, grouped by rule. UNMAPPED must be 0.
    copy     server-side copy old -> new. Idempotent; skips what is already there.
    rewrite  patch the S3 keys recorded INSIDE the copied documents.
    verify   every destination exists, and every key any document names resolves.
    delete   remove the originals. Refuses unless verify passed in this journal.

Every phase is `--dry-run` unless `--apply` is given. They are separate commands
rather than one switch because the ordering is the safety property: nothing is
rewritten before everything is copied, and nothing is deleted before everything
is verified.

WHY REWRITE AT ALL
------------------
A run record holds S3 keys, not URLs (that is the point of `runs.check_bindings`).
Moving the objects without patching the records leaves 134 runs pointing at keys
that no longer exist, so chaining from an old run would fail. The rewrite is what
makes history keep working, not a cosmetic pass.

The journal (`local/migrations/<ts>.json`, git-ignored) records what each phase
did. Nothing about the migration is ever written into the bucket.
"""
from __future__ import annotations

import collections
import contextlib
import datetime as dt
import io
import json
import os
import sys

import click

from studio_pipeline import STUDIO_DIR  # noqa: E402
from studio_pipeline.adapters import s3 as s3c  # noqa: E402
from studio_pipeline.domain import paths as P  # noqa: E402

JOURNAL_DIR = str(STUDIO_DIR / "local" / "migrations")

# Documents whose CONTENT names S3 keys. Everything else is opaque bytes.
JSON_DOCS = ("request.json", "result.json", "scene.json")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


# ── the plan ────────────────────────────────────────────────────────────────

def build_plan(s3) -> dict:
    """Every old key, its rule and its destination. Raises on anything unmapped."""
    moves: list[tuple[str, str, str]] = []   # (rule, old, new)
    markers: list[str] = []
    unmapped: list[str] = []
    already: list[str] = []

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3c.BUCKET):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if not k.startswith(P.LEGACY_PREFIX):
                already.append(k)
                continue
            try:
                hit = P.classify(k)
            except P.PathError as exc:
                unmapped.append(f"{k}  ({exc})")
                continue
            if hit is None:
                markers.append(k)
                continue
            moves.append((hit[0], k, hit[1]))

    return {"moves": moves, "markers": markers, "unmapped": unmapped, "already": already}


def report(plan: dict) -> None:
    by_rule: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for rule, old, new in plan["moves"]:
        by_rule[rule].append((old, new))

    print(f"{'rule':<12} {'n':>5}  what it does")
    print("-" * 78)
    for rule, pattern, note in P.LEGACY_MAP:
        hits = by_rule.get(rule, [])
        print(f"{rule:<12} {len(hits):>5}  {pattern}")
        print(f"{'':<19}{note}")
        if hits:
            old, new = hits[0]
            print(f"{'':<19}e.g. {old}")
            print(f"{'':<24}-> {new}")
    print("-" * 78)
    print(f"{'TOTAL':<12} {len(plan['moves']):>5}  objects to move")
    print(f"{'markers':<12} {len(plan['markers']):>5}  empty folder markers (dropped, not moved)")
    print(f"{'in new tree':<12} {len(plan['already']):>5}  objects already outside media/")
    print(f"{'UNMAPPED':<12} {len(plan['unmapped']):>5}  "
          + ("" if not plan["unmapped"] else "<-- BLOCKS EVERYTHING BELOW"))
    for u in plan["unmapped"]:
        print(f"             {u}")


# ── copy ────────────────────────────────────────────────────────────────────

def head(s3, key: str):
    try:
        return s3.head_object(Bucket=s3c.BUCKET, Key=key)
    except Exception:  # noqa: BLE001 — boto raises ClientError(404) here
        return None


def phase_copy(s3, plan: dict, apply: bool) -> dict:
    copied, skipped, failed = [], [], []
    for _rule, old, new in plan["moves"]:
        src = head(s3, old)
        if src is None:
            failed.append((old, "source vanished"))
            continue
        if src["ContentLength"] > 5 * 1024 ** 3:
            failed.append((old, "over 5 GB — needs a multipart copy"))
            continue
        dst = head(s3, new)
        if dst is not None and dst["ContentLength"] == src["ContentLength"]:
            skipped.append(new)          # resumable: already there, same size
            continue
        if apply:
            s3.copy_object(Bucket=s3c.BUCKET, Key=new,
                           CopySource={"Bucket": s3c.BUCKET, "Key": old},
                           MetadataDirective="COPY")
        copied.append(new)
    return {"copied": copied, "skipped": skipped, "failed": failed}


# ── rewrite ─────────────────────────────────────────────────────────────────

def _relocate_str(v):
    """Any string that is an old key becomes its new key. Everything else passes."""
    if isinstance(v, str) and v.startswith(P.LEGACY_PREFIX):
        try:
            new = P.relocate(v)
        except P.PathError:
            return v, False
        if new:
            return new, True
    return v, False


def walk_relocate(node):
    """Recursive key rewrite — the safety net under the field-specific edits.

    Field-specific handling covers the structural renames (`parts` -> `shots`,
    `owner` -> `project`). This catches every remaining key reference, including
    in fields added after this script was written.
    """
    changed = 0
    if isinstance(node, dict):
        for k, v in list(node.items()):
            new, hit = _relocate_str(v)
            if hit:
                node[k] = new
                changed += 1
            else:
                changed += walk_relocate(v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            new, hit = _relocate_str(v)
            if hit:
                node[i] = new
                changed += 1
            else:
                changed += walk_relocate(v)
    return changed


def rename_key(doc: dict, old: str, new: str) -> dict:
    """Rename a field IN PLACE in the ordering.

    `doc[new] = doc.pop(old)` appends instead, which shuffles a record's fields
    into an order nobody chose — a rewritten `scene.json` would list its output
    before its shots. These documents are read by people, so order is content.
    """
    if old not in doc or new in doc:
        return doc
    out = {}
    for k, v in doc.items():
        out[new if k == old else k] = v
    doc.clear()
    doc.update(out)
    return doc


def insert_after(doc: dict, anchor: str, field: str, value) -> dict:
    """Add a field directly after `anchor`, or at the end if there is no anchor."""
    if field in doc:
        doc[field] = value
        return doc
    out = {}
    for k, v in doc.items():
        out[k] = v
        if k == anchor:
            out[field] = value
    if field not in out:
        out[field] = value
    doc.clear()
    doc.update(out)
    return doc


def _characters_in(bindings) -> list[str]:
    """Which characters a run used, read back out of its bindings.

    A run that cited a character's reference images used that character. Now
    that runs live under a project rather than under a character, this is the
    only place the association survives — so it is recorded explicitly.
    """
    chars = set()
    for val in (bindings or {}).values():
        for v in (val if isinstance(val, list) else [val]):
            if isinstance(v, str) and (c := P.character_of(v)):
                chars.add(c)
    return sorted(chars)


def rewrite_run_doc(doc: dict) -> dict:
    """request.json / result.json: `owner` -> `project`, plus `characters[]`."""
    rename_key(doc, "owner", "project")
    walk_relocate(doc)
    if "bindings" in doc:
        insert_after(doc, "project", "characters", _characters_in(doc.get("bindings")))
    return doc


def rewrite_scene_doc(doc: dict) -> dict:
    """scene.json: parts -> shots, part_key -> shot_key, owner -> project."""
    rename_key(doc, "owner", "project")
    rename_key(doc, "parts", "shots")
    for shot in doc.get("shots", []):
        rename_key(shot, "part_key", "shot_key")
    st = doc.get("stitch")
    if isinstance(st, dict):
        rename_key(st, "uniform_parts", "uniform_shots")
    walk_relocate(doc)
    return doc


def rewrite_chain_doc(doc: dict) -> dict:
    rename_key(doc, "owner", "project")
    walk_relocate(doc)
    return doc


def _reference_index(s3, name: str) -> list[dict]:
    """Seed the profile's reference index from the folder plus any .txt sidecars.

    A description written by hand later replaces the sidecar; seeding from what
    already exists means the index starts populated rather than as 40 blanks.
    """
    entries = []
    prefix = P.char_pool_prefix(name, "reference")
    keys = s3c.list_keys(s3, prefix)
    captions = {}
    for k in keys:
        if k.lower().endswith(".txt"):
            try:
                body = s3.get_object(Bucket=s3c.BUCKET, Key=k)["Body"].read()
                captions[os.path.splitext(k)[0]] = body.decode("utf-8").strip()
            except Exception:  # noqa: BLE001
                pass
    root = s3c.key(prefix) + "/"
    for k in keys:
        if k.lower().endswith(".txt"):
            continue
        entries.append({
            "file": k[len(root):],
            "description": captions.get(os.path.splitext(k)[0], ""),
            "tags": [],
        })
    return entries


def phase_rewrite(s3, plan: dict, apply: bool) -> dict:
    import yaml

    touched, unchanged = [], []
    dests = [new for _r, _o, new in plan["moves"]]

    for new in dests:
        base = os.path.basename(new)
        if base not in JSON_DOCS and base != "profile.yaml":
            continue
        obj = head(s3, new)
        if obj is None:
            die(f"{new} has not been copied yet — run `copy --apply` first")
        body = s3.get_object(Bucket=s3c.BUCKET, Key=new)["Body"].read()

        if base == "profile.yaml":
            doc = yaml.safe_load(body.decode("utf-8")) or {}
            name = P.character_of(new)
            if doc.get("references"):
                unchanged.append(new)
                continue
            doc["references"] = _reference_index(s3, name)
            doc.setdefault("default_set", [])
            out = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                 default_flow_style=False, width=100).encode("utf-8")
            ct = "application/yaml"
        else:
            doc = json.loads(body.decode("utf-8"))
            before = json.dumps(doc, sort_keys=True)
            if base == "scene.json":
                doc = rewrite_scene_doc(doc)
            elif base in ("request.json", "result.json"):
                doc = rewrite_run_doc(doc)
            if json.dumps(doc, sort_keys=True) == before:
                unchanged.append(new)
                continue
            out = (json.dumps(doc, indent=2) + "\n").encode("utf-8")
            ct = "application/json"

        if apply:
            s3.put_object(Bucket=s3c.BUCKET, Key=new, Body=io.BytesIO(out),
                          ContentType=ct)
        touched.append(new)

    # Chain manifests live at projects/<p>/chains/<slug>.json — not a fixed
    # basename, so they are collected by prefix rather than by name.
    for _rule, _old, new in plan["moves"]:
        if "/chains/" not in new or not new.endswith(".json"):
            continue
        if head(s3, new) is None:
            die(f"{new} has not been copied yet — run `copy --apply` first")
        doc = json.loads(s3.get_object(Bucket=s3c.BUCKET, Key=new)["Body"].read())
        before = json.dumps(doc, sort_keys=True)
        doc = rewrite_chain_doc(doc)
        if json.dumps(doc, sort_keys=True) == before:
            unchanged.append(new)
            continue
        if apply:
            s3.put_object(Bucket=s3c.BUCKET, Key=new,
                          Body=io.BytesIO((json.dumps(doc, indent=2) + "\n").encode()),
                          ContentType="application/json")
        touched.append(new)

    return {"rewritten": touched, "unchanged": unchanged}


# ── verify ──────────────────────────────────────────────────────────────────

def _is_document(key: str) -> bool:
    """Documents get rewritten, so their size is EXPECTED to change on the way."""
    return (os.path.basename(key) in JSON_DOCS
            or os.path.basename(key) == "profile.yaml"
            or ("/chains/" in key and key.endswith(".json")))


def phase_verify(s3, plan: dict) -> dict:
    missing_dest, size_mismatch = [], []
    for _rule, old, new in plan["moves"]:
        dst = head(s3, new)
        if dst is None:
            missing_dest.append(new)
            continue
        if _is_document(new):
            continue  # rewritten on purpose — size comparison means nothing here
        src = head(s3, old)
        if src is not None and src["ContentLength"] != dst["ContentLength"]:
            size_mismatch.append(new)

    # The high-value check: every key a surviving document NAMES must resolve.
    #
    # Some do not, and did not before this migration either — `curate.py`
    # renumbered and removed reference images after the runs that cited them, so
    # those records have pointed at gone keys for weeks. The plan enumerates
    # every object that existed pre-migration, so a reference to something that
    # was never a destination was already broken. Those are reported separately:
    # inherited breakage is worth seeing, but it must not block a migration that
    # did not cause it.
    existed = {new for _r, _o, new in plan["moves"]}
    dangling, pre_existing, stale, checked = [], [], [], 0
    resolved: dict[str, bool] = {}
    for _rule, _old, new in plan["moves"]:
        if not (new.endswith(".json") and (os.path.basename(new) in JSON_DOCS
                                           or "/chains/" in new)):
            continue
        if head(s3, new) is None:
            continue
        doc = json.loads(s3.get_object(Bucket=s3c.BUCKET, Key=new)["Body"].read())
        for ref in _collect_keys(doc):
            if ref.startswith(P.LEGACY_PREFIX):
                stale.append(f"{new}: {ref}")
                continue
            checked += 1
            if ref not in resolved:
                resolved[ref] = head(s3, ref) is not None
            if resolved[ref]:
                continue
            (dangling if ref in existed else pre_existing).append(f"{new}: {ref}")

    ok = not (missing_dest or size_mismatch or dangling or stale)
    return {"ok": ok, "missing_dest": missing_dest, "size_mismatch": size_mismatch,
            "dangling": dangling, "pre_existing": pre_existing, "stale": stale,
            "refs_checked": checked}


def _collect_keys(node) -> list[str]:
    """Every string in a document that looks like an S3 key of ours."""
    roots = (P.LEGACY_PREFIX, P.CHARACTERS + "/", P.PROJECTS + "/", "phrasebook/")
    out: list[str] = []
    if isinstance(node, dict):
        for v in node.values():
            out += _collect_keys(v)
    elif isinstance(node, list):
        for v in node:
            out += _collect_keys(v)
    elif isinstance(node, str) and node.startswith(roots) and "://" not in node:
        out.append(node)
    return out


# ── delete ──────────────────────────────────────────────────────────────────

def phase_delete(s3, plan: dict, apply: bool, journal: dict) -> dict:
    if not (journal.get("verify") or {}).get("ok"):
        die("verify has not passed in this journal — run `verify` first. "
            "Deleting before verification is how a migration loses data.")
    deleted = []
    batch: list[dict] = []
    for _rule, old, new in plan["moves"]:
        if head(s3, new) is None:
            die(f"{new} is missing — refusing to delete {old}")
        batch.append({"Key": old})
        deleted.append(old)
        if apply and len(batch) == 1000:
            s3.delete_objects(Bucket=s3c.BUCKET, Delete={"Objects": batch})
            batch = []
    # Folder markers carry no data and have no destination; they go too.
    for marker in plan["markers"]:
        batch.append({"Key": marker})
        deleted.append(marker)
    if apply and batch:
        s3.delete_objects(Bucket=s3c.BUCKET, Delete={"Objects": batch})
    return {"deleted": deleted}


# ── the journal ─────────────────────────────────────────────────────────────

def journal_path(name: str | None) -> str:
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    if name:
        return os.path.join(JOURNAL_DIR, name if name.endswith(".json") else name + ".json")
    existing = sorted(f for f in os.listdir(JOURNAL_DIR) if f.endswith(".json"))
    if existing:
        return os.path.join(JOURNAL_DIR, existing[-1])
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(JOURNAL_DIR, f"{ts}.json")


def load_journal(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {}


def save_journal(path: str, doc: dict) -> None:
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2)


# ── selftest ────────────────────────────────────────────────────────────────

FIXTURE = [
    "media/x/profile.yaml",
    "media/x/reference/x_1.png",
    "media/x/reference/x_1.txt",
    "media/x/input/x_in_12.png",
    "media/x/input/body_positions.jpg",
    "media/x/input/IMG_0001.JPG",
    "media/x/input/Screenshot 2026-01-01 at 1.00.00 AM.heic",
    "media/x/originals/some photo.jpg",
    "media/x/other/a clip.mp4",
    "media/x/trash/a reject.mp4",
    "media/x/favorites/a keeper.mp4",
    "media/x/runs/2026-01-01_00-00-00_slug/request.json",
    "media/x/runs/2026-01-01_00-00-00_slug/output/slug.mp4",
    "media/x/scenes/2026-01-01_00-00-00_s/parts/part-03.mp4",
    "media/x/scenes/2026-01-01_00-00-00_s/scene.json",
    "media/x/scenes/2026-01-01_00-00-00_s/output/s.mp4",
    "media/x/chains/s.json",
    "media/phrasebook/wording.yaml",
    "media/",
    "media/x/trash/",
]

EXPECTED = {
    "media/x/profile.yaml": ("profile", "characters/x/profile.yaml"),
    "media/x/reference/x_1.png": ("reference", "characters/x/reference/x_1.png"),
    "media/x/reference/x_1.txt": ("reference", "characters/x/reference/x_1.txt"),
    "media/x/input/x_in_12.png": ("turnarounds", "characters/x/reference/x_in_12.png"),
    "media/x/input/body_positions.jpg": ("turnarounds", "characters/x/reference/body_positions.jpg"),
    "media/x/input/IMG_0001.JPG": ("uploads", "characters/x/corpus/IMG_0001.JPG"),
    "media/x/input/Screenshot 2026-01-01 at 1.00.00 AM.heic":
        ("uploads", "characters/x/corpus/Screenshot 2026-01-01 at 1.00.00 AM.heic"),
    "media/x/originals/some photo.jpg": ("seed", "characters/x/seed/some photo.jpg"),
    "media/x/other/a clip.mp4": ("corpus", "characters/x/corpus/a clip.mp4"),
    "media/x/trash/a reject.mp4": ("archive", "characters/x/archive/a reject.mp4"),
    "media/x/favorites/a keeper.mp4": ("favorites", "projects/x/favorites/a keeper.mp4"),
    "media/x/runs/2026-01-01_00-00-00_slug/request.json":
        ("runs", "projects/x/runs/2026-01-01_00-00-00_slug/request.json"),
    "media/x/runs/2026-01-01_00-00-00_slug/output/slug.mp4":
        ("runs", "projects/x/runs/2026-01-01_00-00-00_slug/output/slug.mp4"),
    "media/x/scenes/2026-01-01_00-00-00_s/parts/part-03.mp4":
        ("shots", "projects/x/scenes/2026-01-01_00-00-00_s/shots/shot-03.mp4"),
    "media/x/scenes/2026-01-01_00-00-00_s/scene.json":
        ("scenes", "projects/x/scenes/2026-01-01_00-00-00_s/scene.json"),
    "media/x/scenes/2026-01-01_00-00-00_s/output/s.mp4":
        ("scenes", "projects/x/scenes/2026-01-01_00-00-00_s/output/s.mp4"),
    "media/x/chains/s.json": ("chains", "projects/x/chains/s.json"),
    "media/phrasebook/wording.yaml": ("phrasebook", "phrasebook/wording.yaml"),
}


def selftest() -> int:
    """`relocate` must be TOTAL over the key set and IDEMPOTENT. No S3 needed."""
    bad = 0
    for k in FIXTURE:
        got = P.classify(k)
        if k in EXPECTED:
            if got != EXPECTED[k]:
                print(f"FAIL {k}\n  expected {EXPECTED[k]}\n  got      {got}")
                bad += 1
                continue
            if P.relocate(got[1]) is not None:
                print(f"FAIL not idempotent: relocate({got[1]!r}) != None")
                bad += 1
        elif got is not None:
            print(f"FAIL {k}: expected None (folder marker), got {got}")
            bad += 1

    # A document rewrite is idempotent too — running it twice must not drift.
    scene = {"scene": "x/s", "owner": "x",
             "parts": [{"n": 1, "key": "media/x/runs/r/output/a.mp4",
                        "part_key": "media/x/scenes/s/parts/part-01.mp4"}],
             "stitch": {"method": "m", "uniform_parts": True},
             "output": {"key": "media/x/scenes/s/output/s.mp4"}}
    once = rewrite_scene_doc(json.loads(json.dumps(scene)))
    twice = rewrite_scene_doc(json.loads(json.dumps(once)))
    if json.dumps(once, sort_keys=True) != json.dumps(twice, sort_keys=True):
        print("FAIL scene rewrite is not idempotent")
        bad += 1
    if "parts" in once or "part_key" in once["shots"][0]:
        print(f"FAIL scene rewrite left old names: {once}")
        bad += 1

    run = {"run_id": "r", "owner": "x",
           "bindings": {"start_image": "media/x/input/x_in_1.png",
                        "reference_images": ["media/x/reference/x_3.png"]}}
    once = rewrite_run_doc(json.loads(json.dumps(run)))
    twice = rewrite_run_doc(json.loads(json.dumps(once)))
    if json.dumps(once, sort_keys=True) != json.dumps(twice, sort_keys=True):
        print("FAIL run rewrite is not idempotent")
        bad += 1
    if once.get("characters") != ["x"] or once.get("project") != "x":
        print(f"FAIL run rewrite metadata: {once}")
        bad += 1
    if "owner" in once or list(once)[:3] != ["run_id", "project", "characters"]:
        print(f"FAIL run rewrite field order: {list(once)}")
        bad += 1
    if list(twice) != list(once):
        print(f"FAIL run rewrite reorders on a second pass: {list(twice)}")
        bad += 1

    print(f"selftest: {len(FIXTURE)} keys + 2 documents, {bad} failure(s)")
    return 1 if bad else 0


# ── CLI ─────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _session(journal_name, phase, apply=None):
    """The setup and teardown every phase shares.

    Each phase loads the journal, rebuilds the plan, does its work and saves
    the journal back. That sharing is why this was one function with a
    six-way branch; a context manager keeps it without the branch.
    """
    s3 = s3c.client()
    jpath = journal_path(journal_name)
    journal = load_journal(jpath)
    plan = build_plan(s3)
    if phase != "plan":
        if plan["unmapped"]:
            die(f"{len(plan['unmapped'])} unmapped key(s) — run `plan` and fix the map first")
        print(f"[{'APPLY' if apply else 'dry run'}] {phase}: "
              f"{len(plan['moves'])} object(s) in scope\n")
    try:
        yield s3, plan, journal
    finally:
        save_journal(jpath, journal)
        print(f"journal: {jpath}")


@click.group(help=__doc__)
def main():
    pass


@main.command("selftest")
def do_selftest():
    """Check the key mapping against known inputs, without touching S3."""
    raise SystemExit(selftest())


@main.command("plan")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_plan(apply, journal):
    """Show what would move, and record the mapping."""
    with _session(journal, "plan", apply) as (_s3, plan, jrn):
        report(plan)
        jrn["plan"] = {"moves": len(plan["moves"]), "markers": len(plan["markers"]),
                       "unmapped": plan["unmapped"],
                       "map": [[r, o, n] for r, o, n in plan["moves"]]}
    if plan["unmapped"]:
        raise SystemExit(1)


@main.command("copy")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_copy(apply, journal):
    """Copy every mapped object to its new key."""
    with _session(journal, "copy", apply) as (s3, plan, jrn):
        res = phase_copy(s3, plan, apply)
        print(f"copied   {len(res['copied'])}")
        print(f"skipped  {len(res['skipped'])}  (already at the destination)")
        if res["failed"]:
            print(f"FAILED   {len(res['failed'])}")
            for k, why in res["failed"]:
                print(f"  {k}: {why}")
        if apply:
            jrn["copy"] = {"copied": len(res["copied"]), "skipped": len(res["skipped"]),
                           "failed": res["failed"]}
    if res["failed"]:
        raise SystemExit(1)


@main.command("rewrite")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_rewrite(apply, journal):
    """Rewrite the records that name a moved object."""
    with _session(journal, "rewrite", apply) as (s3, plan, jrn):
        res = phase_rewrite(s3, plan, apply)
        print(f"rewritten {len(res['rewritten'])}")
        print(f"unchanged {len(res['unchanged'])}")
        for k in res["rewritten"][:5]:
            print(f"  e.g. {k}")
        if apply:
            jrn["rewrite"] = {"rewritten": len(res["rewritten"]),
                              "unchanged": len(res["unchanged"])}


@main.command("verify")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_verify(apply, journal):
    """Check every destination exists and no record was left dangling."""
    with _session(journal, "verify", apply) as (s3, plan, jrn):
        res = phase_verify(s3, plan)
        print(f"destinations missing   {len(res['missing_dest'])}")
        print(f"size mismatches        {len(res['size_mismatch'])}   (documents excluded — rewritten)")
        print(f"recorded keys checked  {res['refs_checked']}")
        print(f"dangling references    {len(res['dangling'])}   (broken BY this migration)")
        print(f"already broken         {len(res['pre_existing'])}   (gone before it; not blocking)")
        print(f"stale (still media/)   {len(res['stale'])}")
        for label in ("missing_dest", "size_mismatch", "dangling", "stale"):
            for k in res[label][:10]:
                print(f"  {label}: {k}")
        if res["pre_existing"]:
            print("\n  already broken before the migration — reference images that "
                  "`studio curate`\n  renumbered or removed after the runs that cited them:")
            for k in res["pre_existing"][:8]:
                print(f"    {k}")
            if len(res["pre_existing"]) > 8:
                print(f"    … and {len(res['pre_existing']) - 8} more")
        print("\nVERIFY: " + ("PASS" if res["ok"] else "FAIL"))
        jrn["verify"] = {"ok": res["ok"], "refs_checked": res["refs_checked"],
                         "dangling": res["dangling"][:50],
                         "pre_existing": res["pre_existing"],
                         "stale": res["stale"][:50]}
    if not res["ok"]:
        raise SystemExit(1)


@main.command("delete")
@click.option("--apply", is_flag=True, help="actually do it (default is a dry run)")
@click.option("--journal", help="journal file name (default: the newest)")
def do_delete(apply, journal):
    """Remove the originals, once everything else has passed."""
    with _session(journal, "delete", apply) as (s3, plan, jrn):
        res = phase_delete(s3, plan, apply, jrn)
        print(f"{'deleted' if apply else 'would delete'}  {len(res['deleted'])} object(s)")
        if apply:
            jrn["delete"] = {"deleted": len(res["deleted"])}
