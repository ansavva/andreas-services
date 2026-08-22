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

Scenes are copied in for the same reason a scene copies its shots: a movie stays
playable and re-cuttable while its scenes are rebuilt around it, and
`movie.json` records the sceneref beside the copied key, so copying does not
lose lineage. That copy was a server-side `CopyObject` and is a download plus an
upload now — `create` says why the bytes have to travel.

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
import mimetypes
import os
import pathlib
import sys
import tempfile

import click

from studio_pipeline.adapters.ffmpeg import (  # noqa: E402  — the same joiner scenes use
    probe,
    stitch,
)
from studio_pipeline.adapters import store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
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
    """Tree-relative — addresses a FOLDER. Use `movie_key` for get/put."""
    return P.movie_prefix(project, movie_id)


def movie_key(project: str, movie_id: str, *parts: str) -> str:
    return P.movie_key(project, movie_id, *parts)


def list_movies(project: str) -> list[str]:
    """Movie ids in a project, oldest first (ids sort chronologically)."""
    return P.list_ids(P.movies_prefix(project))


def resolve_movie(ref: str, default_project: str | None = None) -> tuple[str, str]:
    """'<project>/<movie_id>' | '<project>/latest' | '<movie_id>' -> (project, id)."""
    if "/" in ref:
        project, mid = ref.split("/", 1)
    elif default_project:
        project, mid = default_project, ref
    else:
        die(f"cannot resolve movie {ref!r}: no project given (use <project>/<movie_id>)")
    ids = list_movies(project)
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

def scene_characters(manifest: dict) -> list[str]:
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
            found.update(R.run_characters(rp, rid))
    return sorted(found)


def create(project: str, slug: str, refs: list[str],
           dest_dir: str | None = None) -> dict:
    """Resolve scenerefs -> copy scenes in -> stitch -> upload -> write movie.json."""
    # Resolve every scene before copying anything, and report ALL the ones that
    # are not cut yet. A scene can now exist as a plan, so "not assembled" is an
    # ordinary state rather than a broken record — being told about them one per
    # attempt would mean one round trip per missing scene.
    resolved = []
    characters: set[str] = set()
    planned: list[str] = []
    for ref in refs:
        sc_project, scene_id = SC.resolve_scene(ref, project)
        manifest = SC.read_manifest(sc_project, scene_id)
        if not manifest:
            die(f"{sc_project}/{scene_id} has no scene.json — it cannot be cut into a movie")
        key = SC.scene_output_key(manifest)
        if not key:
            planned.append(f"{sc_project}/{scene_id}")
            continue
        characters.update(scene_characters(manifest))
        resolved.append({"sceneref": ref, "scene": f"{sc_project}/{scene_id}",
                         "source_key": key})
    if planned:
        die(f"{len(planned)} scene(s) are planned but not assembled:\n  "
            + "\n  ".join(planned)
            + "\n       assemble each one first: "
              f"studio scenes assemble {planned[0]}")

    movie_id = new_movie_id(slug)
    print(f"movie {project}/{movie_id}")

    tmp = tempfile.mkdtemp(prefix="movie-")
    store.folder(movie_key(project, movie_id, "scenes"))
    local: list[str] = []
    for n, scene in enumerate(resolved, 1):
        ext = os.path.splitext(scene["source_key"])[1]
        lp = os.path.join(tmp, f"scene-{n:02d}{ext}")
        store.download(scene["source_key"], pathlib.Path(lp))
        local.append(lp)
        scene["n"] = n
        scene["scene_key"] = movie_key(project, movie_id, "scenes", f"scene-{n:02d}{ext}")
        # A read plus a write where this was a server-side `CopyObject`. Same
        # trade `scenes.assemble` makes and for the same reason — a second node
        # on one blob is copy-on-write (#334), and the API's delete route
        # destroys the shared bytes when either row goes. The file is already
        # local from the download above, so the cost is one PUT per scene.
        store.upload(scene["scene_key"], pathlib.Path(lp),
                     content_type=mimetypes.guess_type(lp)[0] or "application/octet-stream")
        print(f"  scene {n}: {scene['scene']}")

    out_local = os.path.join(tmp, f"{R.slugify(slug)}.mp4")
    info = stitch(local, out_local, label="scenes")
    for scene, pr in zip(resolved, info.pop("probes")):
        scene["duration"] = pr["duration"]

    out_key = movie_key(project, movie_id, "output", f"{R.slugify(slug)}.mp4")
    store.folder(movie_key(project, movie_id, "output"))
    store.upload(out_key, pathlib.Path(out_local), content_type="video/mp4")
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
    R.write_json(movie_key(project, movie_id, "movie.json"), manifest)

    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        keep = os.path.join(dest_dir, os.path.basename(out_local))
        os.replace(out_local, keep)
        manifest["local"] = keep
    return manifest


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
    m = create(project, slug, scene, dest)
    print(json.dumps({k: m[k] for k in ("movie", "output", "stitch")}, indent=2))


@main.command("list")
@click.argument("project", required=True)
def do_list(project):
    """Every movie in a project."""
    ids = list_movies(project)
    if not ids:
        print(f"project {project} has no movies")
    for i in ids:
        print(i)


@main.command("show")
@click.argument("ref", required=True)
@click.option("--project")
def do_show(ref, project):
    """One movie's record."""
    owner, mid = resolve_movie(ref, project)
    print(json.dumps(R.read_json(movie_key(owner, mid, "movie.json")), indent=2))


@main.command("outputs")
@click.argument("ref", required=True)
@click.option("--expires", type=int, default=3600)
@click.option("--presign", is_flag=True)
@click.option("--project")
def do_outputs(ref, expires, presign, project):
    """The finished file(s), as keys or as temporary URLs."""
    _warn_ignored_expiry(expires)
    owner, mid = resolve_movie(ref, project)
    output = movie_prefix(owner, mid) + "/output"
    keys = [f"{output}/{e['name']}" for e in store.files(output)]
    if presign:
        for k, u in zip(keys, R.presign(keys)):
            print(f"{k}\n  {u}")
    else:
        print("\n".join(keys))
