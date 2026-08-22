"""`studio scenes` — the SCENE store: a piece planned, shot, and cut.

A **run** is one submission to a model (see `runs.py`). A **scene** is an ordered
sequence of run outputs stitched into a single continuous video — and, since
storyboards, the plan those runs are made from. It is created before anything
renders and filled in as work lands:

    projects/<project>/scenes/<slug>/
        scene.json      the plan AND the record — shots, panels, runs, the cut
        storyboard/     the panels: shot-<NN>-p<M>.png
        shots/          each source clip, copied in, numbered in cut order
        output/         the stitched scene — <slug>.mp4

Keyed by **slug**, not by timestamp. A scene now outlives any one cut of it, so
naming it after the moment it was assembled stopped making sense. Scenes cut
before this still exist under `<timestamp>_<slug>` and still resolve — to the
resolver both are directory names, and those are finished pieces.

THE WORD "SHOT"
---------------
A scene is made of **shots**, and a shot here is one run's output — the unit a
scene is cut from. It was called a "part" before, which named its position in a
list rather than what it is. Note the term is loaded elsewhere: a Kling
`multi_prompt` cut is a shot *inside* one generation, and the `studio-media-shot`
skill produces a whole still-then-clip chain. The nesting is
generation cut ⊂ shot ⊂ scene ⊂ movie.

WHY SHOTS ARE COPIED IN
-----------------------
`shots/` holds a copy of each clip as it was at cut time, so a scene stays
playable and re-stitchable even as its runs accumulate around it. The manifest
records the originating **runref** alongside the copied key, so lineage is not
lost by copying — `scene.json` names both. The same holds for panels.

RE-CUTTING OVERWRITES
---------------------
`output/<slug>.mp4` is replaced, not versioned by filename, so the scene folder
always shows current state instead of accumulating cuts nobody prunes.

**What makes that recoverable is true of PROD only.** The prod bucket versions
every object and grants no `s3:DeleteObjectVersion`, so a superseded cut is
still there to restore. A per-machine dev stack has no versioning, deliberately
— `infra/modules/dev_storage/main.tf` says why: the recovery there is a re-seed
via `dev-aws-reset.sh`, and version history would only slow the teardown and
bill for bytes nobody restores. Against dev, a re-cut destroys the previous one.

THE STORE IS THE ONLY ORIGIN
----------------------------
Shots were server-side copies within the bucket. They are a download plus an
upload now, so every shot's bytes travel through this process — for a scene that
is video, and a 200 MB clip is the ordinary case. `assemble` says why the copy
has to be real: a second node pointing at one blob is copy-on-write (#334), and
the API's delete route destroys the shared bytes when either row goes. Nothing
is fetched from outside, and no presigned URL is ever stored — `scene.json`
holds paths, exactly as `request.json` does.

STITCHING
---------
Handled by `adapters/ffmpeg.py`, the same layer `movies.py` uses, so a scene and
a movie join their inputs by identical rules: stream-copy when everything already
agrees, re-encode to the first input's geometry (and say so in the manifest) when
it does not. ffmpeg comes from the `imageio-ffmpeg` wheel.

CLI
---
    studio scenes new <project> --slug <slug> --from-json plan.json
    studio scenes plan <project>/<slug>
    studio scenes sheet <project>/<slug>            # the board, as one image
    studio scenes assemble <project>/<slug>
    studio scenes list <project>
    studio scenes show <project>/latest
    studio scenes outputs <project>/latest --presign

The two that spend money — rendering the panels and rendering a shot — live
beside the submit lifecycle they drive, not here.
"""
from __future__ import annotations

import json
import mimetypes
import os
import pathlib
import tempfile

import click

from studio_pipeline.adapters.ffmpeg import (  # noqa: E402  — shared with movies.py and frames.py
    grab,
    probe,
    stitch,
)
from studio_pipeline.adapters import store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
from studio_pipeline import errors  # noqa: E402
from studio_pipeline.domain import contact_sheet  # noqa: E402  — a board is read by looking
from studio_pipeline.domain import frames as FRAMES  # noqa: E402  — the chain and the pool
from studio_pipeline.domain import (
    paths as P,  # noqa: E402  — the one module that knows the bucket's shape
)
from studio_pipeline.domain import (
    runs as R,  # noqa: E402  — the run store; scenes are built from its records
)
from studio_pipeline.domain import (
    storyboard as SB,  # noqa: E402  — the plan a scene is built FROM
)

# What a scene is cut from. Shared with the run store rather than restated, so
# a new container format is legal in both places at once.
VIDEO_EXT = R.VID_EXTS


# ── layout ──────────────────────────────────────────────────────────────────

def scene_prefix(project: str, scene_id: str) -> str:
    """Tree-relative — addresses a FOLDER. Use `scene_key` for get/put."""
    return P.scene_prefix(project, scene_id)


def scene_key(project: str, scene_id: str, *parts: str) -> str:
    return P.scene_key(project, scene_id, *parts)


def list_scenes(project: str) -> list[str]:
    """Scene ids in a project, sorted by id.

    NOT oldest first any more. That held only while every id began with a
    timestamp; slug-keyed ids sort alphabetically and land after every
    timestamped one. `_newest` reads the manifests instead.
    """
    return P.list_ids(P.scenes_prefix(project))


def _newest(project: str, ids: list[str]) -> str:
    """The most recently created scene, read off the manifests.

    Not `ids[-1]`. That worked only while every id began with a timestamp, which
    made the lexical sort accidentally chronological. A scene created today is
    keyed by its slug, and a lexical sort puts every slug after every timestamp —
    so `latest` would have quietly meant "alphabetically last", and `movies new
    --scene <p>/latest` is exactly the caller that would have got it wrong.

    A scene whose manifest is missing or unreadable sorts by its position
    instead, so one half-written scene cannot make the whole resolver fail —
    `latest` is a convenience, and it should not be the thing that stops you
    reaching the scene you actually named.
    """
    def created(scene_id: str) -> str:
        try:
            doc = read_manifest(project, scene_id) or {}
        except Exception:
            return ""
        return doc.get("created") or ""

    return max(enumerate(ids), key=lambda pair: (created(pair[1]), pair[0]))[1]


def resolve_scene(ref: str, default_project: str | None = None) -> tuple[str, str]:
    """'<project>/<scene_id>' | '<project>/latest' | '<scene_id>' -> (project, id).

    Also the sceneref resolver `movies.py` uses — a movie addresses its scenes
    exactly the way a scene addresses its runs.

    A scene is addressed by SLUG. Timestamped ids from before scenes were
    planned rather than assembled still resolve, and permanently: to this
    resolver both are just directory names, and the scenes carrying them are
    finished cuts whose runs are still their history.
    """
    if "/" in ref:
        project, sid = ref.split("/", 1)
    elif default_project:
        project, sid = default_project, ref
    else:
        die(f"cannot resolve scene {ref!r}: no project given (use <project>/<scene_id>)")
    ids = list_scenes(project)
    if not ids:
        die(f"project {project} has no scenes")
    if sid == "latest":
        return project, _newest(project, ids)
    if sid in ids:
        return project, sid
    hits = [i for i in ids if sid in i]
    if len(hits) == 1:
        return project, hits[0]
    if not hits:
        die(f"no scene matching {sid!r} in project {project}")
    die(f"{sid!r} is ambiguous in project {project}: {hits}")


def scene_shots(manifest: dict) -> list[dict]:
    """A scene's shots. Reads the pre-rename `parts` too, so an old manifest
    that escaped the migration still opens instead of looking empty."""
    return manifest.get("shots") or manifest.get("parts") or []


# ── the manifest ────────────────────────────────────────────────────────────

def manifest_key(project: str, scene_id: str) -> str:
    return scene_key(project, scene_id, "scene.json")


def read_manifest(project: str, scene_id: str) -> dict | None:
    """A scene's record, or None when there is no scene there."""
    return R.read_json(manifest_key(project, scene_id))


def write_manifest(manifest: dict) -> dict:
    """Write a scene back, refreshing its derived fields first.

    `status` is recomputed on every write and never read back as authority — the
    same discipline the character index follows. It is in the document so a
    person (or an agent reading `scenes show`) can see where a scene is without
    replaying the rules.

    **The scene's folder is ensured here**, because this is the only place a
    scene is written and `new_scene` writes one that has never existed. S3 made
    `scenes/<slug>/` out of the slashes in the key; the catalog needs the node,
    and without it starting a scene would fail on a parent nobody had made.
    """
    manifest["status"] = SB.scene_status(manifest)
    for shot in manifest.get("shots") or []:
        shot["status"] = SB.shot_status(shot)
    manifest["updated"] = R._now()
    # The id comes off `scene`, not off `slug`: for a scene planned today the
    # two agree, but a scene assembled before scenes were planned is keyed by
    # `<timestamp>_<slug>` and writing it back under its bare slug would put it
    # in a directory that does not exist.
    project, _, scene_id = manifest["scene"].partition("/")
    store.folder(scene_prefix(project, scene_id))
    R.write_json(manifest_key(project, scene_id), manifest)
    return manifest


def is_assembled(manifest: dict) -> bool:
    """Whether this scene has been cut, as opposed to merely planned."""
    return SB.is_assembled(manifest)


def scene_output_key(manifest: dict) -> str | None:
    return (manifest.get("output") or {}).get("key")


# ── starting a scene ────────────────────────────────────────────────────────

def new_scene(project: str, slug: str, plan_path: str | None,
              title: str = "", force: bool = False) -> dict:
    """Ingest a plan and write `scene.json`. Nothing renders, nothing bills.

    Re-ingesting is how a plan is revised, and it must not orphan work already
    paid for — so `--force` merges the revision onto what the scene already has
    rather than replacing it. See `storyboard.merge`.
    """
    SB.check_scene_slug(slug)
    plan = SB.load_plan(plan_path) if plan_path else {"shots": []}
    if title:
        plan["title"] = title

    manifest = SB.normalise(plan, project, slug)
    if plan_path:
        SB.validate(manifest)

    existing = read_manifest(project, slug)
    if existing:
        if not force:
            die(f"{project}/{slug} already exists ({existing.get('status', 'unknown')}).\n"
                f"       Revising a scene means re-ingesting it: pass --force, and "
                f"every run, panel and cut it already has is carried across.")
        manifest = SB.merge(existing, manifest)

    return write_manifest(manifest)


def shot_video_key(shot: dict, project: str) -> str | None:
    """The video a shot rendered, resolved from its run if not already recorded."""
    if shot.get("key"):
        return shot["key"]
    if not shot.get("run"):
        return None
    keys = R.resolve_output_keys(shot.get("runref") or shot["run"],
                                 default_project=project, kinds=VIDEO_EXT)
    if len(keys) > 1:
        die(f"shot {shot.get('id') or shot.get('n')}: its run has {len(keys)} videos; "
            f"record which one by appending #N to the shot's runref")
    return keys[0]


# ── assembling ──────────────────────────────────────────────────────────────

def assemble(project: str, scene_id: str, refs: tuple[str, ...] = (),
             dest_dir: str | None = None) -> dict:
    """Copy each rendered shot in, stitch them, and record the cut.

    Two ways in, and they are the same code path. Normally the shots come from
    the scene's own plan, each one already rendered. `--shot <runref>` appends
    runs directly instead, which is what makes the pre-storyboard one-liner —
    "just stitch these three runs" — still a one-liner: a scene with no plan
    plus a list of runrefs is exactly the old behaviour.

    The cut OVERWRITES `output/<slug>.mp4`. The bucket versions every object and
    grants no `s3:DeleteObjectVersion`, so a previous cut is never destroyed,
    only superseded — and a replace through the API keeps the node's identity,
    so anything already naming the cut still names it.
    """
    manifest = read_manifest(project, scene_id)
    if not manifest:
        die(f"no scene {project}/{scene_id} — start one with "
            f"`studio scenes new {project} --slug {scene_id}`")

    shots = list(scene_shots(manifest))
    characters = set(manifest.get("characters") or [])

    for ref in refs:
        run_project, run_id = R.resolve_run(ref, default_project=project)
        keys = R.resolve_output_keys(ref, default_project=project, kinds=VIDEO_EXT)
        if len(keys) > 1:
            die(f"{ref}: {len(keys)} videos; append #N to pick one")
        characters.update(R.run_characters(run_project, run_id))
        shots.append({"n": len(shots) + 1, "id": f"shot-{len(shots) + 1:02d}",
                      "runref": ref, "run": f"{run_project}/{run_id}", "key": keys[0]})

    if not shots:
        die(f"{project}/{scene_id} has no shots — plan some, or pass --shot <runref>")

    unrendered = [s.get("id") or f"shot {s.get('n')}" for s in shots if not s.get("run")]
    if unrendered:
        die(f"{len(unrendered)} shot(s) have not been rendered: {', '.join(unrendered)}\n"
            f"       studio scenes render {project}/{scene_id} --shot <n>")

    slug = manifest.get("slug") or scene_id
    print(f"scene {project}/{scene_id}")

    tmp = tempfile.mkdtemp(prefix="scene-")
    store.folder(scene_key(project, scene_id, "shots"))
    local: list[str] = []
    for n, shot in enumerate(shots, 1):
        src = shot_video_key(shot, project)
        ext = os.path.splitext(src)[1]
        lp = os.path.join(tmp, f"shot-{n:02d}{ext}")
        store.download(src, pathlib.Path(lp))
        local.append(lp)
        shot["n"] = n
        shot["key"] = src
        shot["shot_key"] = scene_key(project, scene_id, "shots", f"shot-{n:02d}{ext}")
        # **This was a server-side `CopyObject` and is now a read plus a write**,
        # so the bytes travel through this process — and for a scene they are
        # video, which is the case `store.copy` says to reconsider before
        # reaching for. It is accepted here for the reason the alternative is
        # worse: a second node pointing at one blob is copy-on-write (#334), and
        # the API's delete route destroys the shared bytes when either row goes.
        # The upload is already local, so the extra cost is one PUT per shot.
        store.upload(shot["shot_key"], pathlib.Path(lp),
                     content_type=mimetypes.guess_type(lp)[0] or "application/octet-stream")
        print(f"  shot {n}: {shot['run']}")

    out_local = os.path.join(tmp, f"{R.slugify(slug)}.mp4")
    info = stitch(local, out_local, label="shots")
    for shot, pr in zip(shots, info.pop("probes")):
        shot["duration"] = pr["duration"]

    out_key = scene_key(project, scene_id, "output", f"{R.slugify(slug)}.mp4")
    superseded = R.read_json(manifest_key(project, scene_id)) or {}
    store.folder(scene_key(project, scene_id, "output"))
    store.upload(out_key, pathlib.Path(out_local), content_type="video/mp4")

    manifest["characters"] = sorted(characters)
    manifest["shots"] = shots
    manifest["stitch"] = info
    manifest["output"] = {"key": out_key, **probe(out_local)}
    manifest["assembled"] = R._now()
    write_manifest(manifest)

    if scene_output_key(superseded):
        print("  (the previous cut is superseded, not destroyed — it survives as "
              "an object version)")

    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        keep = os.path.join(dest_dir, os.path.basename(out_local))
        os.replace(out_local, keep)
        manifest["local"] = keep
    return manifest


# ── carrying a shot forward ─────────────────────────────────────────────────

def handoff(project: str, scene_id: str, n: int, from_run: str | None = None) -> dict:
    """Take the previous shot's last frame and hand it to shot N.

    Two things, and the second is the point: the frame goes into the project's
    input pool, and is written onto shot N as the frame it opens on. There is no
    third record — `storyboard.scene_frames` reads the sequence back off the
    plan, so the scene's own frames cannot drift from the scene.
    """
    manifest = read_manifest(project, scene_id)
    if not manifest:
        die(f"no scene {project}/{scene_id}")
    shots = scene_shots(manifest)
    by_n = {s.get("n"): s for s in shots}
    shot, previous = by_n.get(n), by_n.get(n - 1)
    if not shot:
        die(f"{project}/{scene_id} has no shot {n} (it has {sorted(by_n)})")
    if not previous:
        die(f"shot {n} is the first shot — there is nothing before it to hand off from")
    ref = from_run or previous.get("runref") or previous.get("run")
    if not ref:
        die(f"shot {previous.get('id')} has not been rendered, so it has no last frame\n"
            f"       studio scenes render {project}/{scene_id} --shot {n - 1}")

    tmp = tempfile.mkdtemp(prefix="handoff-")
    _p, run_id, src = FRAMES.fetch_video(ref, project, tmp)
    local = grab(src, None, os.path.join(tmp, f"{run_id}_last.png"), from_end=0.2)
    key = FRAMES.add_to_input_pool(project, local)

    shot["continues"] = True
    shot["opens_on"] = {"key": key, "from_run": f"{project}/{run_id}"}
    write_manifest(manifest)

    print(key)
    print(f"shot {n} ({shot.get('id')}) now opens on the last frame of "
          f"{previous.get('id')}")
    print(f"the scene's own frames are now: "
          f"{len(SB.scene_frames(manifest))}", flush=True)
    return manifest


# ── reading the plan ────────────────────────────────────────────────────────

def plan_prompts(manifest: dict) -> list[str]:
    """Every word the plan will send, laid out to be read.

    The prompts live in `scene.json` and are therefore already in the bucket,
    but a raw manifest is not a readable thing — a prompt is prose and wants to
    be read as prose before it is paid for.
    """
    out = []
    if manifest.get("setting"):
        out += ["", "=" * 70, "SETTING — prepended to every PANEL prompt", "=" * 70,
                manifest["setting"]]
    for shot in scene_shots(manifest):
        roles = SB.panel_roles(shot)
        out += ["", "=" * 70,
                f"{shot.get('id')}  —  {shot.get('beat', '')}".rstrip(),
                "=" * 70]
        for panel, role in zip(shot.get("panels") or [], roles):
            if SB.is_supplied(panel):
                out += [f"--- panel {panel['n']} [{role}] — supplied image, no prompt",
                        f"    {panel.get('key')}"]
                continue
            out += [f"--- panel {panel['n']} [{role}]  ({panel.get('model')})",
                    panel.get("prompt") or ""]
        motion = shot.get("motion") or {}
        out += [f"--- motion  ({motion.get('model')}, {motion.get('duration')}s)",
                motion.get("prompt") or ""]
    return out


def plan_table(manifest: dict) -> list[str]:
    """The plan as lines you can scan — `show` stays raw JSON for machines."""
    out = [f"{manifest['scene']}  [{manifest.get('status', '?')}]"]
    if manifest.get("title"):
        out.append(f"  {manifest['title']}")
    for shot in scene_shots(manifest):
        roles = SB.panel_roles(shot)
        panels = shot.get("panels") or []
        bits = []
        for panel, role in zip(panels, roles):
            mark = "*" if panel.get("key") else "-"
            stale = "!" if panel.get("stale") else ""
            bits.append(f"{mark}p{panel['n']}[{role}]{stale}")
        motion = shot.get("motion") or {}
        out.append(
            f"  {shot.get('id', '?'):<10} {shot.get('status', '?'):<9} "
            f"{motion.get('model', '?')} {motion.get('duration', '?')}s  "
            f"{' '.join(bits) or '(no panels)'}  {shot.get('beat', '')}".rstrip())
    if any(p.get("stale") for s in scene_shots(manifest) for p in s.get("panels") or []):
        out.append("  ! = the panel on disk predates its prompt")
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────

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


@click.group(help=__doc__)
def main():
    pass


@main.command("new")
@click.argument("project", required=True)
@click.option("--force", is_flag=True,
              help="revise an existing scene, carrying its runs and panels across")
@click.option("--from-json", "from_json",
              help="the plan: shots, panels and the motion that carries them")
@click.option("--part", hidden=True, multiple=True)
@click.option("--shot", hidden=True, multiple=True)
@click.option("--slug", required=True)
@click.option("--title", default="")
@errors.reports(SB.PlanError, P.PathError)
def do_new(project, force, from_json, part, shot, slug, title):
    """Start a scene from a plan."""
    # `--shot`/`--part` used to assemble a cut here. They are kept visible to
    # the parser and answered with a redirect, because a silent "unknown
    # option" on a command that still exists reads as a broken install.
    if shot or part:
        die("`scenes new` starts a scene from a plan; it no longer assembles one.\n"
            f"       studio scenes new {project} --slug {slug}\n"
            f"       studio scenes assemble {project}/{slug} "
            + " ".join(f"--shot {r}" for r in (*shot, *part)))
    m = new_scene(project, slug, from_json, title, force)
    print("\n".join(plan_table(m)))
    print(f"\nnext: studio scenes check {m['scene']}")


@main.command("assemble")
@click.argument("ref", required=True)
@click.option("--dest", help="also keep the stitched file locally")
@click.option("--project")
@click.option("--shot", multiple=True,
              help=("a run output to append, in cut order. Repeatable. Accepts "
                    "<project>/<run_id>, <run_id>, a unique slug fragment, or #N."))
def do_assemble(ref, dest, project, shot):
    """Cut a scene's rendered shots into one continuous take."""
    owner, sid = resolve_scene(ref, project)
    m = assemble(owner, sid, shot, dest)
    print(json.dumps({k: m[k] for k in ("scene", "output", "stitch")}, indent=2))


@main.command("handoff")
@click.argument("ref", required=True)
@click.option("--from-run", "from_run",
              help="the run to take the frame from (default: the previous shot's)")
@click.option("--project")
@click.option("--shot", type=int, required=True,
              help="the shot that should OPEN on this frame")
def do_handoff(ref, from_run, project, shot):
    """Carry the previous shot's last frame into the next one."""
    owner, sid = resolve_scene(ref, project)
    handoff(owner, sid, shot, from_run)


@main.command("plan")
@click.argument("ref", required=True)
@click.option("--project")
@click.option("--prompts", is_flag=True,
              help="also print every prompt in full — what each panel and each shot says")
def do_plan(ref, project, prompts):
    """A scene's plan, as a table rather than as JSON."""
    owner, sid = resolve_scene(ref, project)
    manifest = read_manifest(owner, sid)
    if not manifest:
        die(f"no scene.json for {owner}/{sid}")
    print("\n".join(plan_table(manifest)))
    if prompts:
        print("\n".join(plan_prompts(manifest)))


@main.command("sheet")
@click.argument("ref", required=True)
@click.option("--cell", type=int, default=320)
@click.option("--cols", type=int, default=4)
@click.option("--out", help="where to write the sheet (default: a temp directory)")
@click.option("--project")
def do_sheet(ref, cols, cell, out, project):
    """The whole board as one captioned contact sheet.

    A board only means anything looked at. This is also the only way an agent
    can read its own storyboard, which is why `frames grid` exists for clips.
    """
    owner, sid = resolve_scene(ref, project)
    manifest = read_manifest(owner, sid)
    if not manifest:
        die(f"no scene.json for {owner}/{sid}")
    captions = SB.sheet_captions(manifest)
    if not captions:
        die(f"{owner}/{sid} has no panels yet — studio scenes board {owner}/{sid}")

    tmp = tempfile.mkdtemp(prefix="board-")
    paths, labels = [], []
    for key, caption in captions:
        lp = os.path.join(tmp, os.path.basename(key))
        store.download(key, pathlib.Path(lp))
        paths.append(lp)
        labels.append(caption)
    dest = os.path.join(out or tmp, f"{manifest.get('slug', sid)}-board.png")
    local = contact_sheet.build(paths, dest, cols=cols, cell=cell, captions=labels)
    # The board is the thing someone looks at to judge the scene. Leaving it on
    # local disk means only whoever ran the command can see it.
    key = scene_key(owner, sid, "review", "board.png")
    store.folder(scene_key(owner, sid, "review"))
    store.upload(key, pathlib.Path(local), content_type="image/png")
    print(key)
    if out:
        print(f"  (local copy: {local})")


@main.command("list")
@click.argument("project", required=True)
def do_list(project):
    """Every scene in a project."""
    ids = list_scenes(project)
    if not ids:
        print(f"project {project} has no scenes")
    for i in ids:
        print(i)


@main.command("show")
@click.argument("ref", required=True)
@click.option("--project")
def do_show(ref, project):
    """One scene's record."""
    owner, sid = resolve_scene(ref, project)
    print(json.dumps(R.read_json(scene_key(owner, sid, "scene.json")), indent=2))


@main.command("outputs")
@click.argument("ref", required=True)
@click.option("--expires", type=int, default=3600)
@click.option("--presign", is_flag=True)
@click.option("--project")
def do_outputs(ref, expires, presign, project):
    """The stitched file(s), as keys or as temporary URLs."""
    _warn_ignored_expiry(expires)
    owner, sid = resolve_scene(ref, project)
    output = P.scene_prefix(owner, sid) + "/output"
    keys = [f"{output}/{e['name']}" for e in store.files(output)]
    if presign:
        for k, u in zip(keys, R.presign(keys)):
            print(f"{k}\n  {u}")
    else:
        print("\n".join(keys))
