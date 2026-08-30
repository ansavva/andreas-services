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

STITCHING IS A RENDER JOB — SAME ARRANGEMENT AS A SCENE
--------------------------------------------------------
This section used to say the opposite: `ffmpeg` ships in this wheel and the
Lambda has none, so `create` downloads each scene's cut, stitches here and
uploads the result. That was a statement about an image, and the image changed.

`create` resolves every sceneref to a cut, creates the movie row, and enqueues
**one render job**. The worker copies each scene's cut into `scenes/`, stitches
by the same rules a scene is stitched by, uploads the movie and records
`output`, `stitch`, `cuts` and `assembled` on the row.

What stays here is resolution and refusal — `latest`, a unique fragment, "these
three scenes are planned but not assembled" — because those are sentences with an
action in them and belong in front of the person.

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
import sys

import click

from studio_pipeline.adapters import api, entities, store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
from studio_pipeline import errors  # noqa: E402
from studio_pipeline.domain import projects as PROJECTS  # noqa: E402
from studio_pipeline.domain import renders as RENDER  # noqa: E402  — the encode lives there now
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
    # `.get`, for the reason `scenes.resolve_scene` spells out: rows written
    # before the listing projection carried `slug` do not have one.
    hits = [m for m in found if m.get("slug") == mid]
    if not hits:
        hits = [m for m in found if mid in (m.get("slug") or "")]
    if len(hits) == 1:
        return entities.get_movie(hits[0]["id"])
    if not hits:
        die(f"no movie matching {mid!r} in project {record['slug']}")
    die(f"{mid!r} is ambiguous in project {record['slug']}: "
        + ", ".join(f"{m['id']} ({m.get('slug') or '-'})" for m in hits[:5]))


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
    """Resolve scenerefs -> create the movie -> ask the service to cut it.

    The record is created **before** any bytes move, so a failure halfway leaves
    a movie with no output — visible, re-runnable, and holding the order that is
    the only thing a movie contributes. The other way round would leave copied
    scene files parented to a folder nothing names.

    **The copy into `scenes/` is the worker's now**, along with the stitch and the
    record. It is still a download plus an upload rather than a server-side
    `CopyObject`, and for the reason it always was: a second node on one blob is
    copy-on-write (#334), and the API's delete route destroys the shared bytes
    when either row goes. What changed is where the two hops happen — inside one
    Lambda with the file already on its disk, instead of through a terminal.
    """
    # Resolve every scene before anything is created, and report ALL the ones
    # that are not cut yet. A scene can exist as a plan, so "not assembled" is an
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
    for n, scene in enumerate(resolved, 1):
        print(f"  scene {n}: {scene['slug']}  ({scene['scene']})")

    # **Scene IDS on the edge rows, the per-cut detail in the stitch report.**
    # `put_movie_scenes` validates every entry as an id, and sending the resolved
    # dicts here once answered 500 after every scene had been copied and the
    # finished cut uploaded. The worker records the copied node, the duration and
    # the position under `stitch.cuts`, which is where `scenes assemble` already
    # puts the same kind of thing.
    entities.put_movie_scenes(record["id"], [scene["scene"] for scene in resolved])
    result = RENDER.submit("assemble", {
        "target": record["id"],
        "parts": [RENDER.part(scene["source_node"], scene=scene["scene"],
                              slug=scene["slug"]) for scene in resolved],
        "characters": sorted(characters),
    }, what="the cut")

    record = entities.get_movie(record["id"])
    if result.get("re_encoded"):
        print(f"  ({result['stitch']['method']})")
    if dest_dir:
        record = {**record, "local": RENDER.fetch(result["output"], dest_dir)}
    return record


# ── CLI ─────────────────────────────────────────────────────────────────────

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
@errors.reports(R.RunError, api.ApiError, RENDER.RenderError)
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
        print(f"{movie['id']}  {(movie.get('slug') or '-'):<24} "
              f"{movie.get('status', '?'):<10} "
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
@click.option("--presign", is_flag=True)
@click.option("--project")
@errors.reports(api.ApiError)
def do_outputs(ref, presign, project):
    """The finished file(s), as node ids or as temporary URLs."""
    record = resolve_movie(ref, project)
    folder = store.child(record["folder"], OUTPUT_FOLDER)
    entries = store.files_of(folder["id"]) if folder else []
    for entry in entries:
        if presign:
            print(f"{entry['id']}  {entry['name']}\n  "
                  f"{store.presign_node(entry['id'])}")
        else:
            print(f"{entry['id']}  {entry['name']}")
