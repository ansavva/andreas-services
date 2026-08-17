"""`studio scenes` — the shared SCENE store: many runs assembled into one cut.

A **run** is one submission to a model (see `runs.py`). A **scene** is an
ordered sequence of run outputs stitched into a single continuous video, kept
together under the project it belongs to:

    projects/<project>/scenes/<YYYY-MM-DD_HH-MM-SS>_<slug>/
        scene.json      the manifest — ordered shots as RUNREFS and S3 KEYS
        shots/          each source clip, copied in, numbered in cut order
        output/         the stitched scene — <slug>.mp4

Same id shape as a run (`<timestamp>_<slug>`), same project, same rule that the
record OWNS its output. A scene is **derived**, never a source of truth: the
runs it names remain the history, and a scene can always be rebuilt from them.

THE WORD "SHOT"
---------------
A scene is made of **shots**, and a shot here is one run's output — the unit a
scene is cut from. It was called a "part" before, which named its position in a
list rather than what it is. Note the term is loaded elsewhere: a Kling
`multi_prompt` cut is a shot *inside* one generation, and the `studio-shot`
skill produces a whole still-then-clip chain. The nesting is
generation cut ⊂ shot ⊂ scene ⊂ movie.

WHY SHOTS ARE COPIED IN
-----------------------
`shots/` holds a copy of each clip as it was at cut time, so a scene stays
playable and re-stitchable even as its runs accumulate around it. The manifest
records the originating **runref** alongside the copied key, so lineage is not
lost by copying — `scene.json` names both.

S3 IS THE ONLY ORIGIN
---------------------
Shots are server-side copies within the bucket; only the stitched output is
uploaded. Nothing is fetched from outside, and no presigned URL is ever stored —
`scene.json` holds S3 keys, exactly as `request.json` does.

STITCHING
---------
Handled by `video.py`, the same layer `movies.py` uses, so a scene and a movie
join their inputs by identical rules: stream-copy when everything already
agrees, re-encode to the first input's geometry (and say so in the manifest)
when it does not. ffmpeg comes from the `imageio-ffmpeg` wheel.

CLI
---
    studio scenes new <project> --slug <slug> --shot <runref> --shot <runref> …
    studio scenes list <project>
    studio scenes show <project>/latest
    studio scenes outputs <project>/latest --presign
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile

import click

from studio_pipeline.adapters.ffmpeg import (  # noqa: E402  — shared with movies.py and frames.py
    probe,
    stitch,
)
from studio_pipeline.adapters.s3 import BUCKET, client, die, list_keys  # noqa: E402
from studio_pipeline.domain import (
    paths as P,  # noqa: E402  — the one module that knows the bucket's shape
)
from studio_pipeline.domain import (
    runs as R,  # noqa: E402  — the run store; scenes are built from its records
)

# ── layout ──────────────────────────────────────────────────────────────────

def new_scene_id(slug: str, when: dt.datetime | None = None) -> str:
    """Same id shape as a run: <YYYY-MM-DD_HH-MM-SS>_<slug>."""
    return R.new_run_id(slug, when)


def scene_prefix(project: str, scene_id: str) -> str:
    """Tree-relative — feeds `list_keys`. Use `scene_key` for get/put."""
    return P.scene_prefix(project, scene_id)


def scene_key(project: str, scene_id: str, *parts: str) -> str:
    return P.scene_key(project, scene_id, *parts)


def list_scenes(s3, project: str) -> list[str]:
    """Scene ids in a project, oldest first (ids sort chronologically)."""
    return P.list_ids(s3, P.scenes_prefix(project))


def resolve_scene(s3, ref: str, default_project: str | None = None) -> tuple[str, str]:
    """'<project>/<scene_id>' | '<project>/latest' | '<scene_id>' -> (project, id).

    Also the sceneref resolver `movies.py` uses — a movie addresses its scenes
    exactly the way a scene addresses its runs.
    """
    if "/" in ref:
        project, sid = ref.split("/", 1)
    elif default_project:
        project, sid = default_project, ref
    else:
        die(f"cannot resolve scene {ref!r}: no project given (use <project>/<scene_id>)")
    ids = list_scenes(s3, project)
    if not ids:
        die(f"project {project} has no scenes")
    if sid == "latest":
        return project, ids[-1]
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


# ── build ───────────────────────────────────────────────────────────────────

def create(s3, project: str, slug: str, refs: list[str], dest_dir: str | None = None) -> dict:
    """Resolve runrefs -> copy shots in -> stitch -> upload -> write scene.json."""
    resolved = []
    characters: set[str] = set()
    for ref in refs:
        keys = R.resolve_output_keys(s3, ref, default_project=project)
        vids = [k for k in keys if k.lower().endswith((".mp4", ".mov", ".m4v"))]
        if not vids:
            die(f"{ref}: no video output (got {keys or 'nothing'}) — "
                f"append #N to pick one output")
        if len(vids) > 1:
            die(f"{ref}: {len(vids)} videos; append #N to pick one")
        run_project, run_id = R.resolve_run(s3, ref, default_project=project)
        characters.update(R.run_characters(s3, run_project, run_id))
        resolved.append({"runref": ref, "run": f"{run_project}/{run_id}", "key": vids[0]})

    scene_id = new_scene_id(slug)
    print(f"scene {project}/{scene_id}")

    tmp = tempfile.mkdtemp(prefix="scene-")
    local: list[str] = []
    for n, shot in enumerate(resolved, 1):
        ext = os.path.splitext(shot["key"])[1]
        lp = os.path.join(tmp, f"shot-{n:02d}{ext}")
        s3.download_file(BUCKET, shot["key"], lp)
        local.append(lp)
        shot["n"] = n
        shot["shot_key"] = scene_key(project, scene_id, "shots", f"shot-{n:02d}{ext}")
        # Server-side copy: the bytes never leave the bucket.
        s3.copy_object(Bucket=BUCKET, Key=shot["shot_key"],
                       CopySource={"Bucket": BUCKET, "Key": shot["key"]})
        print(f"  shot {n}: {shot['run']}")

    out_local = os.path.join(tmp, f"{R.slugify(slug)}.mp4")
    info = stitch(local, out_local, label="shots")
    for shot, pr in zip(resolved, info.pop("probes")):
        shot["duration"] = pr["duration"]

    out_key = scene_key(project, scene_id, "output", f"{R.slugify(slug)}.mp4")
    s3.upload_file(out_local, BUCKET, out_key, ExtraArgs={"ContentType": "video/mp4"})
    final = probe(out_local)

    manifest = {
        "scene": f"{project}/{scene_id}",
        "project": project,
        "characters": sorted(characters),
        "slug": R.slugify(slug),
        "created": R._now(),
        "shots": resolved,
        "stitch": info,
        "output": {"key": out_key, **final},
    }
    R.write_json(s3, scene_key(project, scene_id, "scene.json"), manifest)

    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        keep = os.path.join(dest_dir, os.path.basename(out_local))
        os.replace(out_local, keep)
        manifest["local"] = keep
    return manifest


# ── CLI ─────────────────────────────────────────────────────────────────────

@click.group(help=__doc__)
def main():
    pass


@main.command("new")
@click.argument("project", required=True)
@click.option("--dest", help="also keep the stitched file locally")
@click.option("--part", hidden=True, multiple=True)
@click.option("--shot", multiple=True,
              help=("a run output, in cut order. Repeatable. Accepts "
                    "<project>/<run_id>, <run_id>, a unique slug fragment, or #N."))
@click.option("--slug", required=True)
def do_new(project, dest, part, shot, slug):
    """Assemble runs into one continuous cut."""
    # `--part` is the old spelling of `--shot`, kept working and hidden. In
    # argparse both wrote the same dest; Click gives two separate values, so
    # the merge has to happen here or the alias is silently ignored.
    shots = list(shot) + list(part)
    if not shots:
        die("a scene needs at least one --shot <runref>")
    m = create(client(), project, slug, shots, dest)
    print(json.dumps({k: m[k] for k in ("scene", "output", "stitch")}, indent=2))


@main.command("list")
@click.argument("project", required=True)
def do_list(project):
    """Every scene in a project."""
    ids = list_scenes(client(), project)
    if not ids:
        print(f"project {project} has no scenes")
    for i in ids:
        print(i)


@main.command("show")
@click.argument("ref", required=True)
@click.option("--project")
def do_show(ref, project):
    """One scene's record."""
    s3 = client()
    owner, sid = resolve_scene(s3, ref, project)
    print(json.dumps(R.read_json(s3, scene_key(owner, sid, "scene.json")), indent=2))


@main.command("outputs")
@click.argument("ref", required=True)
@click.option("--expires", type=int, default=3600)
@click.option("--presign", is_flag=True)
@click.option("--project")
def do_outputs(ref, expires, presign, project):
    """The stitched file(s), as keys or as temporary URLs."""
    s3 = client()
    owner, sid = resolve_scene(s3, ref, project)
    keys = list_keys(s3, P.scene_prefix(owner, sid) + "/output/")
    if presign:
        for k, u in zip(keys, R.presign(s3, keys, expires)):
            print(f"{k}\n  {u}")
    else:
        print("\n".join(keys))
