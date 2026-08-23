"""`studio movies` — the MOVIE store: several scenes cut into one piece.

The hierarchy, each tier built from the one below it:

    generation cut  a shot inside one submission (Kling `multi_prompt`)
    run             one submission to a model                  (runs.py)
    shot            one run's output, as a scene component     (scenes.py)
    scene           shots stitched into one continuous take    (scenes.py)
    movie           scenes cut together into one piece         (this)

A movie is a **row**, `movie-<uuid>`, addressed by id and labelled by a slug:

    the row      id, project, slug, title, status, scenes (SCENE IDS, in cut
                 order), characters, folder, output, stitch
    the folder   the tree the record names as `folder`:
                     scenes/   each scene's output, copied in, in cut order
                     output/   the finished movie

**`movie.json` is gone**, and so is the `<timestamp>_<slug>` folder name that
was its id. A movie is listed by `GET /api/movies?project=` and ordered by
`created` on the row; its folder is named by `folder` rather than derived from a
slug, so renaming it strands nothing.

DERIVED, NEVER A SOURCE OF TRUTH
--------------------------------
A movie names its scenes; the scenes name their runs; the runs are the history.
So a movie can always be rebuilt, and nothing about it is worth protecting
except the ORDER — which is the one thing it actually contributes. That order is
`scenes` on the record: a list of scene ids, which survive every rename of every
scene in it.

Scenes are copied in for the same reason a scene copies its shots: a movie stays
playable and re-cuttable while its scenes are rebuilt around it, and the copy
sits beside the scene id, so copying does not lose lineage. That copy was a
server-side `CopyObject` and is a download plus an upload now — `create` says why
the bytes have to travel.

STITCHING STAYS LOCAL — SAME ARRANGEMENT AS A SCENE
----------------------------------------------------
`ffmpeg` ships in this wheel and the Lambda behind the API has none, so `create`
downloads each scene's cut, stitches here, uploads through the URL
`POST /api/movies/<id>/output` signs, and `PATCH`es the record. **The API owns
the record, not the encode.**

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
from studio_pipeline.adapters import api, entities, store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
from studio_pipeline import errors  # noqa: E402
from studio_pipeline.domain import projects as PROJECTS  # noqa: E402
from studio_pipeline.domain import runs as R  # noqa: E402
from studio_pipeline.domain import (
    scenes as SC,  # noqa: E402  — for sceneref resolution, not for ffmpeg
)

#: Folders inside a movie's own folder. Convention, resolved by name and created
#: if absent; the record names one node (`folder`) and no map of these.
SCENES_FOLDER = "scenes"
OUTPUT_FOLDER = "output"


# ── addressing ──────────────────────────────────────────────────────────────

def list_movies(project: dict) -> list[dict]:
    """A project's movies, newest first.

    Sorted here rather than trusted off the wire, for the reason
    `scenes.list_scenes` gives: `latest` meaning "the newest one" is this
    module's promise, and a promise resting on somebody else's default ordering
    is not one.
    """
    found = entities.query_movies(project=project["id"]).get("movies") or []
    return sorted(found, key=lambda m: m.get("created") or "", reverse=True)


def resolve_movie(ref: str, default_project: str | None = None) -> dict:
    """'<project>/<slug>' | '<project>/latest' | '<slug>' | 'movie-<uuid>' -> the RECORD.

    The **record**, not a `(project, id)` pair — same shape as
    `runs.resolve_run` and `scenes.resolve_scene`, and for the same reason:
    every caller reads the movie next, and a pair meant a second round trip.

    `latest` is `created` on the row. It used to be `ids[-1]` over folder names,
    which was only chronological because every id began with a timestamp.
    """
    if "/" in ref:
        project, mid = ref.split("/", 1)
    else:
        project, mid = default_project, ref
    if mid.startswith("movie-"):
        try:
            return entities.get_movie(mid)
        except api.NotFound:
            die(f"no movie {mid}")
    if not project:
        die(f"cannot resolve movie {ref!r}: no project given (use <project>/<slug>)")

    record = PROJECTS.require_project(project)
    found = list_movies(record)
    if not found:
        die(f"project {record['slug']} has no movies")
    if mid in ("latest", "last"):
        return entities.get_movie(found[0]["id"])
    hits = [m for m in found if m["slug"] == mid]
    if not hits:
        hits = [m for m in found if mid in m["slug"]]
    if len(hits) == 1:
        return entities.get_movie(hits[0]["id"])
    if not hits:
        die(f"no movie matching {mid!r} in project {record['slug']}")
    die(f"{mid!r} is ambiguous in project {record['slug']}: "
        + ", ".join(f"{m['id']} ({m['slug']})" for m in hits[:5]))


def movie_folder(record: dict, *names: str) -> str:
    """A folder inside the movie's own folder, created if it is absent."""
    return store.folder_path(record["folder"], *names)["id"]


# ── build ───────────────────────────────────────────────────────────────────

def scene_characters(record: dict) -> list[str]:
    """Whose likeness is in a scene, as character ids.

    A scene records this on its row, written by `scenes assemble` from the runs
    behind its shots. It is read straight off rather than recomputed — the walk
    this used to fall back to (ask every shot's run) existed because a scene cut
    before scenes carried the field had no answer, and there is nowhere left for
    a scene without the field to come from: the row is created with it.
    """
    return list(record.get("characters") or [])


def create(project: dict, slug: str, refs: list[str],
           dest_dir: str | None = None) -> dict:
    """Resolve scenerefs -> create the movie -> copy scenes in -> stitch -> record.

    The record is created **before** any bytes move, so a failure halfway leaves
    a movie with no output — visible, re-runnable, and holding the order that is
    the only thing a movie contributes. The other way round would leave copied
    scene files parented to a folder nothing names.
    """
    # Resolve every scene before copying anything, and report ALL the ones that
    # are not cut yet. A scene can exist as a plan, so "not assembled" is an
    # ordinary state rather than a broken record — being told about them one per
    # attempt would mean one round trip per missing scene.
    resolved = []
    characters: set[str] = set()
    planned: list[str] = []
    for ref in refs:
        scene = SC.resolve_scene(ref, project["id"])
        node = SC.scene_output_node(scene)
        if not node:
            planned.append(f"{scene['slug']} ({scene['id']})")
            continue
        characters.update(scene_characters(scene))
        resolved.append({"sceneref": ref, "scene": scene["id"],
                         "slug": scene["slug"], "source_node": node})
    if planned:
        die(f"{len(planned)} scene(s) are planned but not assembled:\n  "
            + "\n  ".join(planned)
            + "\n       assemble each one first: "
              f"studio scenes assemble {planned[0].split(' ')[0]}")

    record = entities.create_movie(project=project["id"], slug=R.slugify(slug),
                                   scenes=[s["scene"] for s in resolved])
    print(f"movie {record['slug']}  ({record['id']})")

    tmp = tempfile.mkdtemp(prefix="movie-")
    scenes_folder = movie_folder(record, SCENES_FOLDER)
    local: list[str] = []
    for n, scene in enumerate(resolved, 1):
        name = store.node(scene["source_node"]).get("name") or "scene.mp4"
        ext = os.path.splitext(name)[1] or ".mp4"
        lp = os.path.join(tmp, f"scene-{n:02d}{ext}")
        store.download_node(scene["source_node"], pathlib.Path(lp))
        local.append(lp)
        scene["n"] = n
        # A read plus a write where this was a server-side `CopyObject`. Same
        # trade `scenes.assemble` makes and for the same reason — a second node
        # on one blob is copy-on-write (#334), and the API's delete route
        # destroys the shared bytes when either row goes. The file is already
        # local from the download above, so the cost is one PUT per scene.
        copied = store.upload_into(
            scenes_folder, f"scene-{n:02d}{ext}", pathlib.Path(lp),
            content_type=mimetypes.guess_type(lp)[0] or "application/octet-stream")
        scene["node"] = copied["id"]
        print(f"  scene {n}: {scene['slug']}  ({scene['scene']})")

    out_local = os.path.join(tmp, f"{R.slugify(slug)}.mp4")
    info = stitch(local, out_local, label="scenes")
    for scene, pr in zip(resolved, info.pop("probes")):
        scene["duration"] = pr["duration"]

    signed = entities.movie_output(record["id"], f"{R.slugify(slug)}.mp4",
                                   os.path.getsize(out_local), "video/mp4")
    store.upload_to_url(signed, pathlib.Path(out_local))

    entities.put_movie_scenes(record["id"], resolved)
    record = entities.patch_movie(
        record["id"], characters=sorted(characters), stitch=info, status="assembled",
        output={"node": signed["node"], **probe(out_local)}, assembled=R._now())

    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        keep = os.path.join(dest_dir, os.path.basename(out_local))
        os.replace(out_local, keep)
        record = {**record, "local": keep}
    return record


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
                    "<project>/<slug>, a scene id, latest, or a unique fragment."))
@click.option("--slug", required=True)
@errors.reports(R.RunError, api.ApiError)
def do_new(project, dest, scene, slug):
    """Cut a project's scenes into one movie."""
    if len(scene) < 2:
        print("note: a one-scene movie is just that scene — cutting it copies the "
              "file for no gain.", file=sys.stderr)
    record = create(PROJECTS.require_project(project), slug, list(scene), dest)
    print(json.dumps({"movie": record["id"], "slug": record["slug"],
                      "output": record.get("output"),
                      "stitch": record.get("stitch")}, indent=2))


@main.command("list")
@click.argument("project", required=True)
@errors.reports(api.ApiError)
def do_list(project):
    """Every movie in a project, newest first."""
    found = list_movies(PROJECTS.require_project(project))
    if not found:
        print(f"project {project} has no movies")
    for movie in found:
        print(f"{movie['id']}  {movie['slug']:<24} {movie.get('status', '?'):<10} "
              f"{(movie.get('created') or '')[:16]}")


@main.command("show")
@click.argument("ref", required=True)
@click.option("--project")
@errors.reports(api.ApiError)
def do_show(ref, project):
    """One movie's record."""
    print(json.dumps(resolve_movie(ref, project), indent=2))


@main.command("outputs")
@click.argument("ref", required=True)
@click.option("--expires", type=int, default=3600)
@click.option("--presign", is_flag=True)
@click.option("--project")
@errors.reports(api.ApiError)
def do_outputs(ref, expires, presign, project):
    """The finished file(s), as node ids or as temporary URLs."""
    _warn_ignored_expiry(expires)
    record = resolve_movie(ref, project)
    folder = store.child(record["folder"], OUTPUT_FOLDER)
    entries = store.files_of(folder["id"]) if folder else []
    for entry in entries:
        if presign:
            print(f"{entry['id']}  {entry['name']}\n  "
                  f"{store.presign_node(entry['id'])}")
        else:
            print(f"{entry['id']}  {entry['name']}")
