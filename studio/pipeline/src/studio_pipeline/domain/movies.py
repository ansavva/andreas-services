"""`studio movies` — the MOVIE store: several scenes cut into one piece.

The hierarchy, each tier built from the one below it:

    generation cut  a shot inside one submission (Kling `multi_prompt`)
    run             one submission to a model                  (runs.py)
    shot            one run's output, as a scene component     (scenes.py)
    scene           shots stitched into one continuous take    (scenes.py)
    movie           scenes cut together into one piece         (this)

    projects/<project>/movies/<YYYY-MM-DD_HH-MM-SS>_<slug>/
        movie.json      the manifest — scenes in cut order, as SCENEREFS and KEYS
        scenes/         each scene's output, copied in, numbered in cut order
        output/         the finished movie — <slug>.mp4

Same id shape as a run and a scene, same project, same rule that the record OWNS
its output.

DERIVED, NEVER A SOURCE OF TRUTH
--------------------------------
A movie names its scenes; the scenes name their runs; the runs are the history.
So a movie can always be rebuilt, and nothing about it is worth protecting
except the ORDER — which is the one thing it actually contributes.

Scenes are copied in server-side for the same reason a scene copies its shots:
a movie stays playable and re-cuttable while its scenes are rebuilt around it,
and `movie.json` records the sceneref beside the copied key, so copying does not
lose lineage.

A SCENE OR A LONGER SCENE?
--------------------------
Cut a movie when the piece has genuine breaks in it — a change of place, of
time, of subject. Extend a scene (studio-media-scene) when it must read as one
continuous take. The stitcher does not care; the audience does. A movie's cut
points are hard cuts, so put them where a hard cut belongs.

CLI
---
    studio movies new <project> --slug <slug> --scene <ref> --scene <ref> …
    studio movies list <project>
    studio movies show <project>/latest
    studio movies outputs <project>/latest --presign
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile

import click

from studio_pipeline.adapters.ffmpeg import (  # noqa: E402  — the same joiner scenes use
    probe,
    stitch,
)
from studio_pipeline.adapters.s3 import BUCKET, client, die, list_keys  # noqa: E402
from studio_pipeline.domain import paths as P  # noqa: E402
from studio_pipeline.domain import runs as R  # noqa: E402
from studio_pipeline.domain import (
    scenes as SC,  # noqa: E402  — for sceneref resolution, not for ffmpeg
)

# ── layout ──────────────────────────────────────────────────────────────────

def new_movie_id(slug: str, when: dt.datetime | None = None) -> str:
    """Same id shape as a run and a scene: <YYYY-MM-DD_HH-MM-SS>_<slug>."""
    return R.new_run_id(slug, when)


def movie_prefix(project: str, movie_id: str) -> str:
    """Tree-relative — feeds `list_keys`. Use `movie_key` for get/put."""
    return P.movie_prefix(project, movie_id)


def movie_key(project: str, movie_id: str, *parts: str) -> str:
    return P.movie_key(project, movie_id, *parts)


def list_movies(s3, project: str) -> list[str]:
    """Movie ids in a project, oldest first (ids sort chronologically)."""
    return P.list_ids(s3, P.movies_prefix(project))


def resolve_movie(s3, ref: str, default_project: str | None = None) -> tuple[str, str]:
    """'<project>/<movie_id>' | '<project>/latest' | '<movie_id>' -> (project, id)."""
    if "/" in ref:
        project, mid = ref.split("/", 1)
    elif default_project:
        project, mid = default_project, ref
    else:
        die(f"cannot resolve movie {ref!r}: no project given (use <project>/<movie_id>)")
    ids = list_movies(s3, project)
    if not ids:
        die(f"project {project} has no movies")
    if mid == "latest":
        return project, ids[-1]
    if mid in ids:
        return project, mid
    hits = [i for i in ids if mid in i]
    if len(hits) == 1:
        return project, hits[0]
    if not hits:
        die(f"no movie matching {mid!r} in project {project}")
    die(f"{mid!r} is ambiguous in project {project}: {hits}")


# ── build ───────────────────────────────────────────────────────────────────

def resolve_scene_output(s3, project: str, scene_id: str) -> tuple[str, dict]:
    """A scene's finished video, read off its manifest.

    Read rather than listed: a scene has exactly one output and its manifest
    already names it, so listing `output/` would be a second call that can only
    agree or be wrong.
    """
    manifest = R.read_json(s3, SC.scene_key(project, scene_id, "scene.json"))
    if not manifest:
        die(f"{project}/{scene_id} has no scene.json — it cannot be cut into a movie")
    key = (manifest.get("output") or {}).get("key")
    if not key:
        die(f"{project}/{scene_id} has no output recorded in its scene.json")
    return key, manifest


def scene_characters(s3, manifest: dict) -> list[str]:
    """Whose likeness is in a scene.

    A scene records this itself now. One built before it did does not, so fall
    back to asking the runs behind its shots — the answer exists either way,
    and a movie that cannot name its cast is a worse outcome than one extra
    read per shot.
    """
    if manifest.get("characters"):
        return manifest["characters"]
    found: set[str] = set()
    for shot in SC.scene_shots(manifest):
        run = shot.get("run") or ""
        if "/" in run:
            rp, rid = run.split("/", 1)
            found.update(R.run_characters(s3, rp, rid))
    return sorted(found)


def create(s3, project: str, slug: str, refs: list[str],
           dest_dir: str | None = None) -> dict:
    """Resolve scenerefs -> copy scenes in -> stitch -> upload -> write movie.json."""
    resolved = []
    characters: set[str] = set()
    for ref in refs:
        sc_project, scene_id = SC.resolve_scene(s3, ref, project)
        key, manifest = resolve_scene_output(s3, sc_project, scene_id)
        characters.update(scene_characters(s3, manifest))
        resolved.append({"sceneref": ref, "scene": f"{sc_project}/{scene_id}",
                         "source_key": key})

    movie_id = new_movie_id(slug)
    print(f"movie {project}/{movie_id}")

    tmp = tempfile.mkdtemp(prefix="movie-")
    local: list[str] = []
    for n, scene in enumerate(resolved, 1):
        ext = os.path.splitext(scene["source_key"])[1]
        lp = os.path.join(tmp, f"scene-{n:02d}{ext}")
        s3.download_file(BUCKET, scene["source_key"], lp)
        local.append(lp)
        scene["n"] = n
        scene["scene_key"] = movie_key(project, movie_id, "scenes", f"scene-{n:02d}{ext}")
        # Server-side copy: the bytes never leave the bucket.
        s3.copy_object(Bucket=BUCKET, Key=scene["scene_key"],
                       CopySource={"Bucket": BUCKET, "Key": scene["source_key"]})
        print(f"  scene {n}: {scene['scene']}")

    out_local = os.path.join(tmp, f"{R.slugify(slug)}.mp4")
    info = stitch(local, out_local, label="scenes")
    for scene, pr in zip(resolved, info.pop("probes")):
        scene["duration"] = pr["duration"]

    out_key = movie_key(project, movie_id, "output", f"{R.slugify(slug)}.mp4")
    s3.upload_file(out_local, BUCKET, out_key, ExtraArgs={"ContentType": "video/mp4"})
    final = probe(out_local)

    manifest = {
        "movie": f"{project}/{movie_id}",
        "project": project,
        "characters": sorted(characters),
        "slug": R.slugify(slug),
        "created": R._now(),
        "scenes": resolved,
        "stitch": info,
        "output": {"key": out_key, **final},
    }
    R.write_json(s3, movie_key(project, movie_id, "movie.json"), manifest)

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
@click.option("--dest", help="also keep the finished file locally")
@click.option("--scene", multiple=True, required=True,
              help=("a scene, in cut order. Repeatable. Accepts "
                    "<project>/<scene_id>, <scene_id>, latest, or a unique fragment."))
@click.option("--slug", required=True)
def do_new(project, dest, scene, slug):
    """Cut a project's scenes into one movie."""
    if len(scene) < 2:
        print("note: a one-scene movie is just that scene — cutting it copies the "
              "file for no gain.", file=sys.stderr)
    m = create(client(), project, slug, scene, dest)
    print(json.dumps({k: m[k] for k in ("movie", "output", "stitch")}, indent=2))


@main.command("list")
@click.argument("project", required=True)
def do_list(project):
    """Every movie in a project."""
    ids = list_movies(client(), project)
    if not ids:
        print(f"project {project} has no movies")
    for i in ids:
        print(i)


@main.command("show")
@click.argument("ref", required=True)
@click.option("--project")
def do_show(ref, project):
    """One movie's record."""
    s3 = client()
    owner, mid = resolve_movie(s3, ref, project)
    print(json.dumps(R.read_json(s3, movie_key(owner, mid, "movie.json")), indent=2))


@main.command("outputs")
@click.argument("ref", required=True)
@click.option("--expires", type=int, default=3600)
@click.option("--presign", is_flag=True)
@click.option("--project")
def do_outputs(ref, expires, presign, project):
    """The finished file(s), as keys or as temporary URLs."""
    s3 = client()
    owner, mid = resolve_movie(s3, ref, project)
    keys = list_keys(s3, movie_prefix(owner, mid) + "/output/")
    if presign:
        for k, u in zip(keys, R.presign(s3, keys, expires)):
            print(f"{k}\n  {u}")
    else:
        print("\n".join(keys))
