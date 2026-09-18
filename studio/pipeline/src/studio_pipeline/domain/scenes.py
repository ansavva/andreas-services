"""`studio scenes` — the SCENE store: a named, ordered series of runs.

A **run** is one submission to a model (see `runs.py`). A **scene** is the tier
above it: the runs made for one continuous piece, and the order its clips are
stitched in. Nothing else.

WHAT A SCENE IS
---------------
A **row**, `scene-<uuid>`, addressed by id and labelled by a free-text name,
holding two facts:

    a run belongs to a scene    `scene` on the RUN record — stills and clips
                                alike, every run made for the piece
    the cut, in order           `runs` on the SCENE record — the video runs,
                                in stitch order; duplicates legal

    the row      id, project, name, status, characters, folder,
                 output, cuts, stitch, assembled, error, runs
    the folder   the tree the record names as `folder`:
                     shots/    each clip, copied in at cut time, in cut order
                     output/   the stitched scene, and the cuts before it

A scene *was* a data model of its own — a plan of shot rows with panels,
prompts, a run each rendered into and the frame each opened on, and seven
commands over it. Every one of those things was already a run: a panel is an
image run, a shot is a video run, the frame it opened on is that run's `start`
send. The plan was a second description of the same runs, kept in step by
hand, and it drifted. So the plan is gone and the cut is the plan: it may name
a run that has not rendered yet, and `assemble` refuses until every run in it
has a clip.

**Membership and the cut are two writes.** `studio run --scene <ref>` files a
run under a scene as it is made; `scenes add` puts a run into the cut, which
joins it to the scene if it was in none. Taking a run out of the cut leaves it
in the scene — the seed frame and the contact sheets were never in the cut and
belong to the scene all the same.

**Every image a scene holds is a node id.** The copied clips, the cut itself,
and the frames. A key is invalidated by any rename of the file it names; a
node id is not.

THE SCENE'S OWN FRAMES
----------------------
`frames` on the record is DERIVED on read: for each run in the cut, in order,
the node of its first `start`-role send. That is the seed shot 1 started from
plus every handoff since — what shot N+1 should be handed as references rather
than the character's curated set (`studio-media-scene` says why). `studio
scenes frames <ref> --args` prints them as `--key …` pairs; `--max N` keeps
the seed and the newest, because every engine caps its references. There is
no second list to keep in step: `frames chain` is for a sequence with no
scene behind it.

RE-CUTTING KEEPS THE ONE BEFORE IT
---------------------------------
Each cut is its own node: the first is `<name>.mp4` and later ones take a
suffix, `<name>-2.mp4` and up. `output` names the newest and `cuts` lists the
rest, newest first.

Accumulating rather than replacing, because a replaced cut is not *visible*: an
S3 object version has no node, so nothing lists it, nothing draws it and
nothing links to it. A person who re-cuts a scene after re-rendering one shot
wants the two takes side by side, which is the thing re-cutting is for. Old
cuts are deletable like any other node.

STITCHING IS THE SERVICE'S
--------------------------
`assemble` resolves each run in the cut to one video node, enqueues **one
render job** and waits for it. The worker downloads, copies each clip into
`shots/`, stitches, uploads the cut and records it on the scene — the last of
those because a cut that reached the bucket and never reached the record is a
failure nobody can see.

Two things stay true:

* **The joining rules are shared with a movie.** `backend/studio_core/media/ffmpeg.py`
  is the same layer `movies` goes through, so a scene and a movie join their
  inputs identically: stream-copy when everything already agrees, re-encode to
  the first input's geometry when it does not — **and say so on the record**.
  That last clause is the one thing that must never be lost in a port: a worker
  that re-encoded silently would be a quality regression nobody could see.
* **Resolution stays here.** `latest`, `#N`, "this run has three clips", "these
  two runs have no video yet" are refusals with an action in them, and a person
  should read them before a job is queued rather than after one fails.

CLI
---
    studio scenes new <project> --name <name> [--run <runref>]...
    studio scenes list <project>
    studio scenes show <project>/<name>
    studio scenes add <project>/<name> <runref>...
    studio scenes remove <project>/<name> <runref>...
    studio scenes order <project>/<name> <runref>...
    studio scenes frames <project>/<name> [--args] [--max N]
    studio scenes assemble <project>/<name> [--shot <runref>]...
    studio scenes outputs <project>/latest --presign

    studio run … --scene <project>/<name>       # file a run under a scene
    studio runs list <project> --scene <name>   # the runs that belong to it

Nothing here spends money. The runs a scene is made of come from `studio run`,
which is where the payload is shown and the submit is typed.
"""
from __future__ import annotations

import json

import click

from studio_pipeline import links as LINKS  # noqa: E402
from studio_pipeline.adapters import api, entities, store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
from studio_pipeline import errors  # noqa: E402
from studio_pipeline.domain import renders as RENDER  # noqa: E402  — the encode lives there
from studio_pipeline.domain import projects as PROJECTS  # noqa: E402
from studio_pipeline.domain import (
    runs as R,  # noqa: E402  — the run store; a scene is a series of its records
)

# What a scene is cut from. Shared with the run store rather than restated, so
# a new container format is legal in both places at once.
VIDEO_EXT = R.VID_EXTS

#: The folder inside a scene's own folder that holds its cuts. Convention,
#: resolved by name and created if absent — the scene record names one node
#: (`folder`) and no map of these.
#:
#: **`shots/` is not here, and its absence is the point.** It holds the per-clip
#: copies an assemble leaves behind, and an assemble is a job on the render queue
#: — `services/render.py` names that folder and creates it. A constant kept on
#: this side would be a second spelling of a name this package never writes, and
#: the two could disagree with nothing to notice.
OUTPUT_FOLDER = "output"


# ── addressing ──────────────────────────────────────────────────────────────

def resolve_scene(ref: str, default_project: str | None = None) -> dict:
    """'<project>/<name>' | '<project>/latest' | '<name>' | 'scene-<uuid>' -> the RECORD.

    Returns the **record**, not a `(project, id)` pair, exactly as
    `runs.resolve_run` does and for the same reason: every caller went straight
    on to read the scene, and a pair meant a second round trip plus two more
    strings to keep in step. It is also the sceneref resolver `movies.py` and
    `studio run --scene` use — a movie addresses its scenes the way a scene
    addresses its runs.

    An id resolves directly and needs no project, which is what makes a record
    that stored a scene id self-sufficient.

    **`latest` is `created` on the row**, never a sort over names: a lexical
    sort would quietly mean "alphabetically last", and `movies new --scene
    <project>/latest` is the caller that would get it wrong.
    """
    if "/" in ref:
        project, sid = ref.split("/", 1)
    else:
        project, sid = default_project, ref
    if sid.startswith("scene-"):
        try:
            return with_project(entities.get_scene(sid))
        except api.NotFound:
            die(f"no scene {sid}")
    if not project:
        die(f"cannot resolve scene {ref!r}: no project given (use <project>/<name>)")

    record = PROJECTS.require_project(project)
    found = list_scenes(record)
    if not found:
        die(f"project {record['name']} has no scenes")
    if sid in ("latest", "last"):
        return with_project(entities.get_scene(found[0]["id"]))
    # `.get`, not `[...]`: a listing row may carry no label, and reading it as
    # a required key turns that into a traceback on every command that
    # addresses a scene by name.
    #
    # **A name is not unique.** A duplicate is ordinary, so the ambiguity
    # branch below is an answer rather than a corner nobody reaches.
    hits = [s for s in found if s.get("name") == sid]
    if not hits:
        hits = [s for s in found if sid in (s.get("name") or "")]
    if len(hits) == 1:
        return with_project(entities.get_scene(hits[0]["id"]))
    if not hits:
        die(f"no scene matching {sid!r} in project {record['name']}")
    die(f"{sid!r} is ambiguous in project {record['name']}: "
        + ", ".join(f"{s['id']} ({s.get('name') or '-'})" for s in hits[:5]))


def with_project(record: dict) -> dict:
    """A scene record carrying `project_name` and `label`, for printing.

    **Two display fields, added once, because a record holds ids and a person
    reads names.** Derived on read, never stored: a stored `<project>/<label>`
    string goes stale the moment either is renamed.

    One extra `GET /api/projects/<id>` per resolve, and only when a caller
    actually needs to print something. `resolve_scene` does it because every one
    of its callers does.
    """
    if record.get("project_name"):
        return record
    name = PROJECTS.resolve(record["project"])["name"]
    return {**record, "project_name": name,
            "label": f"{name}/{record.get('name') or record['id']}"}


def list_scenes(project: dict) -> list[dict]:
    """A project's scenes, newest first.

    Sorted here rather than trusted off the wire. The route's ordering is the
    API's business and may reasonably change; `latest` meaning "the newest one"
    is this module's promise to `movies new --scene <project>/latest`, and a
    promise that depends on somebody else's default is not one.
    """
    found = entities.query_scenes(project=project["id"]).get("scenes") or []
    return sorted(found, key=lambda s: s.get("created") or "", reverse=True)


def cut_ids(record: dict) -> list[str]:
    """The cut as run ids, in order. The record answers it as rows."""
    return [row["id"] for row in record.get("runs") or []]


def scene_output_node(record: dict) -> str | None:
    """The node id of the stitched cut, or None while the scene is only planned."""
    return (record.get("output") or {}).get("node")


def scene_frames(record: dict, max_n: int | None = None) -> list[str]:
    """The scene's own frames as node ids: seed first, then each handoff.

    Read off the record — the API derives the list from the cut's `start`
    sends — and trimmed here, because the cap is an engine's and the person
    typing `--max 7` is the one who knows which engine. Trimming drops the
    OLDEST middle frames: the seed anchors the look the whole scene inherits
    and the newest frames carry the current state, so both ends are kept. The
    same rule as `frames.chain_nodes`, spelled twice because the two lists
    come from different places and one function over both would need to know
    which shape it was handed.
    """
    nodes = [f["node"] for f in record.get("frames") or [] if f.get("node")]
    if max_n is None or len(nodes) <= max_n:
        return nodes
    # `nodes[-0:]` is the WHOLE list, not the empty one, so `--max 1` would
    # silently return every frame and the cap would do nothing.
    return [nodes[0]] + (nodes[-(max_n - 1):] if max_n > 1 else [])


# ── the scene's folders ─────────────────────────────────────────────────────

def scene_folder(record: dict, *names: str) -> str:
    """A folder inside the scene's own folder, created if it is absent.

    The record names one node and no map of blessed folder names, so these are
    resolved by name at write time and made when missing. Renaming `output/`
    strands nothing: the record names every cut by node id.
    """
    return store.folder_path(record["folder"], *names)["id"]


# ── the cut ─────────────────────────────────────────────────────────────────

def resolve_runs(refs: tuple[str, ...] | list[str], project: str) -> list[str]:
    """Runrefs -> run ids, in the order given. Every ref before any write.

    `#N` is refused here: it picks one OUTPUT of a run, and the cut names runs.
    Which clip a run contributes is decided at `assemble` time, where a run
    with two videos is a refusal a person reads rather than a silent first.
    """
    ids = []
    for ref in refs:
        if "#" in ref:
            die(f"{ref}: the cut names runs, not outputs — drop the #N")
        ids.append(R.resolve_run(ref, default_project=project)["id"])
    return ids


def set_cut(record: dict, run_ids: list[str]) -> dict:
    """Write the cut and read the scene back.

    `PATCH /api/scenes/<id>/runs` is a REPLACE and answers with the cut alone,
    so the record is re-read rather than patched together here: the write may
    have joined runs to the scene, and `frames` changes with the cut.
    """
    entities.put_scene_runs(record["id"], run_ids)
    return with_project(entities.get_scene(record["id"]))


def add_runs(record: dict, refs: tuple[str, ...]) -> dict:
    """Append to the cut. A run already in it is appended again — a reprise."""
    return set_cut(record, cut_ids(record) + resolve_runs(refs, record["project"]))


def remove_runs(record: dict, refs: tuple[str, ...]) -> dict:
    """Take runs out of the cut. **Membership is untouched**, by design.

    Every occurrence goes: a reprise is the same run twice, and "remove this
    run" means the run. The run stays in the scene — it was made for it — and
    `PATCH /api/runs/<id>` with `scene: null` is how it leaves, deliberately a
    different act from re-ordering a cut.
    """
    gone = set(resolve_runs(refs, record["project"]))
    kept = [run_id for run_id in cut_ids(record) if run_id not in gone]
    missing = gone - set(cut_ids(record))
    if missing:
        die(f"not in the cut of {record['label']}: {', '.join(sorted(missing))}")
    return set_cut(record, kept)


def order_runs(record: dict, refs: tuple[str, ...]) -> dict:
    """Replace the cut with exactly this order."""
    return set_cut(record, resolve_runs(refs, record["project"]))


# ── starting a scene ────────────────────────────────────────────────────────

def new_scene(project: dict, name: str, refs: tuple[str, ...] = ()) -> dict:
    """A scene row, with its cut if `--run` was given. Nothing renders, nothing bills.

    Refs are resolved before the row is created so a typo in one leaves no
    empty scene behind. The API validates the cut — same project, a video, not
    in another scene — and a refusal there is a 400 with the run named.

    **No uniqueness on the name.** A name is a label; two scenes may share one
    and `resolve_scene` says so when asked for it.
    """
    runs = resolve_runs(refs, project["id"])
    record = entities.create_scene(project=project["id"], name=name, runs=runs)
    return with_project(record)


# ── assembling ──────────────────────────────────────────────────────────────

def assemble(record: dict, refs: tuple[str, ...] = (),
             dest_dir: str | None = None) -> dict:
    """Resolve every run in the cut to a clip, ask the service to cut them, record it.

    `--shot <runref>` replaces the cut first — `order`, then the stitch — which
    is what keeps the pre-plan one-liner a one-liner: a fresh scene plus a list
    of runrefs is "just stitch these three runs", and the cut it leaves behind
    is the record of what was stitched.

    **The encode is a render job.** This resolves, enqueues one job and waits;
    the worker downloads each clip, copies it into `shots/`, stitches, uploads
    the cut and writes `output`, `stitch`, `cuts`, `assembled` and the status
    onto the scene. What stays here is every refusal a person can act on — a run
    with no video yet, a run with two — because those belong in front of the
    person and not at the far end of a queue.

    Every unrendered run is named at once: being told one per attempt is one
    round trip each.

    The bytes never pass through this machine: a four-shot 1080p scene is
    roughly a gigabyte, which no terminal should move to produce a file that
    then goes back up.
    """
    if refs:
        record = order_runs(record, refs)
    project = record["project"]
    cut = cut_ids(record)
    if not cut:
        die(f"{record['label']} has nothing in its cut — "
            f"studio scenes add {record['label']} <runref>…")

    # Resolved once per run, then laid out in cut order — a reprise is the same
    # clip twice, not two lookups.
    clips: dict[str, str] = {}
    characters: set[str] = set()
    unrendered = []
    for run_id in dict.fromkeys(cut):
        run = R.resolve_run(run_id, default_project=project)
        characters.update(run.get("characters") or [])
        try:
            nodes = R.resolve_output_nodes(run_id, default_project=project,
                                           kinds=VIDEO_EXT)
        except R.RunError:
            unrendered.append(run_id)
            continue
        clips[run_id] = RENDER.one_video(nodes, run_id)
    if unrendered:
        die(f"{len(unrendered)} run(s) in the cut have no video yet: "
            f"{', '.join(unrendered)}\n"
            f"       render them, or take them out: "
            f"studio scenes remove {record['label']} <runref>")

    print(f"scene {record['name']}  ({record['id']})")
    parts = [RENDER.part(clips[run_id], run=run_id) for run_id in cut]
    for n, run_id in enumerate(cut, 1):
        print(f"  shot {n}: {run_id}")
    # The cut lands on the scene — `output` on its record — so the scene page
    # is where it is watched; each shot's run page is one click down from it.
    scene_link = LINKS.scene(record)
    if scene_link:
        print(LINKS.ui_line(scene_link, indent="  "))

    result = RENDER.submit("assemble", {"target": record["id"], "parts": parts,
                                        "characters": sorted(characters)},
                           what="the cut")

    superseded = scene_output_node(record)
    # Re-read rather than restated: the worker wrote the output and the stitch
    # report, so the record it produced is the current one and anything this
    # process asserted would be a second opinion.
    record = with_project(entities.get_scene(record["id"]))

    if result.get("re_encoded"):
        # **Said out loud, because it is a quality fact about the file.** The
        # stitcher normalises to the first input's geometry when the clips
        # disagree, and the report on the record says so — but a person watching
        # a terminal should not have to go and read the record to find out.
        print(f"  ({result['stitch']['method']})")
    if superseded:
        print(f"  (the previous cut is kept — {superseded} — and listed under "
              f"`cuts` on the scene)")

    if dest_dir:
        record = {**record, "local": RENDER.fetch(result["output"], dest_dir)}
    return record


# ── printing ────────────────────────────────────────────────────────────────

def cut_lines(record: dict) -> list[str]:
    """The cut as lines a person scans — `show` stays raw JSON for machines."""
    out = [f"{record['label']}  ({record['id']})  [{record.get('status', '?')}]"]
    rows = record.get("runs") or []
    if not rows:
        out.append("  (nothing in the cut yet)")
    for n, row in enumerate(rows, 1):
        clip = (row.get("output") or {}).get("name") or "-"
        out.append(f"  {n:>2}  {row['id']}  {(row.get('status') or '?'):<10} "
                   f"{(row.get('model') or ''):<28} {clip}")
    link = LINKS.scene(record)
    if link:
        out.append(LINKS.ui_line(link, indent="  "))
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────

@click.group(help=__doc__)
def main():
    pass


_RUNREF = ("Accepts <project>/latest, a run id, a unique fragment — a runref, "
           "as `studio runs` spells it. Repeatable, in cut order.")


@main.command("new")
@click.argument("project", required=True)
@click.option("--name", required=True, help="What the scene is called. A label, not an address.")
@click.option("--run", "run", multiple=True,
              help="A video run for the cut, appended in the order given. " + _RUNREF)
@errors.reports(R.RunError, api.ApiError)
def do_new(project, name, run):
    """Start a scene: a name in a project, and optionally its cut."""
    record = new_scene(PROJECTS.require_project(project), name, run)
    print("\n".join(cut_lines(record)))
    print(f"\nnext: studio run … --scene {record['label']}")


@main.command("list")
@click.argument("project", required=True)
@errors.reports(api.ApiError)
def do_list(project):
    """Every scene in a project, newest first."""
    found = list_scenes(PROJECTS.require_project(project))
    if not found:
        print(f"project {project} has no scenes")
    for scene in found:
        print(f"{scene['id']}  {(scene.get('name') or '-'):<24} "
              f"{scene.get('status', '?'):<10} "
              f"{(scene.get('created') or '')[:16]}")


@main.command("show")
@click.argument("ref", required=True)
@click.option("--project")
@errors.reports(api.ApiError)
def do_show(ref, project):
    """One scene's record: its cut as rows, its frames, the movies above it."""
    record = resolve_scene(ref, project)
    print(json.dumps(LINKS.with_ui(record, LINKS.scene(record)), indent=2))


@main.command("add")
@click.argument("ref", required=True)
@click.argument("runref", nargs=-1, required=True)
@click.option("--project")
@errors.reports(R.RunError, api.ApiError)
def do_add(ref, runref, project):
    """Append runs to the cut. A run in no scene joins this one."""
    print("\n".join(cut_lines(add_runs(resolve_scene(ref, project), runref))))


@main.command("remove")
@click.argument("ref", required=True)
@click.argument("runref", nargs=-1, required=True)
@click.option("--project")
@errors.reports(R.RunError, api.ApiError)
def do_remove(ref, runref, project):
    """Take runs out of the cut. They stay in the scene."""
    print("\n".join(cut_lines(remove_runs(resolve_scene(ref, project), runref))))


@main.command("order")
@click.argument("ref", required=True)
@click.argument("runref", nargs=-1, required=True)
@click.option("--project")
@errors.reports(R.RunError, api.ApiError)
def do_order(ref, runref, project):
    """Replace the cut with exactly these runs, in this order."""
    print("\n".join(cut_lines(order_runs(resolve_scene(ref, project), runref))))


@main.command("frames")
@click.argument("ref", required=True)
@click.option("--args", is_flag=True,
              help="print as `--key N --key N …`, ready to paste into a run")
@click.option("--max", "max_", type=int,
              help="cap the list (Kling takes 7); keeps the seed and the newest")
@click.option("--project")
@errors.reports(api.ApiError)
def do_frames(ref, args, max_, project):
    """The scene's own frames: the seed, then each handoff, as node ids.

    Derived from the cut — the first `start` frame each run in it opened on —
    so there is nothing to record and nothing to drift.
    """
    record = resolve_scene(ref, project)
    nodes = scene_frames(record, max_)
    if not nodes:
        die(f"{record['label']} has no frames yet — its cut names no run that "
            f"opened on a start frame")
    if args:
        print(" ".join(f"--key {n}" for n in nodes))
    else:
        for node in nodes:
            print(node)


@main.command("assemble")
@click.argument("ref", required=True)
@click.option("--dest", help="also keep the stitched file locally")
@click.option("--project")
@click.option("--shot", multiple=True,
              help="Replace the cut with these runs first, then stitch. " + _RUNREF)
@errors.reports(R.RunError, api.ApiError, RENDER.RenderError)
def do_assemble(ref, dest, project, shot):
    """Cut the scene's runs into one continuous take."""
    record = assemble(resolve_scene(ref, project), shot, dest)
    print(json.dumps(LINKS.with_ui({"scene": record["id"], "name": record.get("name"),
                                    "output": record.get("output"),
                                    "stitch": record.get("stitch")},
                                   LINKS.scene(record)), indent=2))


@main.command("outputs")
@click.argument("ref", required=True)
@click.option("--presign", is_flag=True)
@click.option("--project")
@errors.reports(api.ApiError)
def do_outputs(ref, presign, project):
    """The stitched file(s), as node ids or as temporary URLs."""
    record = resolve_scene(ref, project)
    folder = store.child(record["folder"], OUTPUT_FOLDER)
    entries = store.files_of(folder["id"]) if folder else []
    for entry in entries:
        if presign:
            print(f"{entry['id']}  {entry['name']}\n  "
                  f"{store.presign_node(entry['id'])}")
        else:
            print(f"{entry['id']}  {entry['name']}")
