"""`studio scenes` — the SCENE store: a piece planned, shot, and cut.

A **run** is one submission to a model (see `runs.py`). A **scene** is an ordered
sequence of run outputs stitched into a single continuous video — and, since
storyboards, the plan those runs are made from.

WHAT A SCENE IS NOW
-------------------
A **row**, `scene-<uuid>`, addressed by id and labelled by a free-text name:

    the row      id, project, name, setting, defaults, status,
                 characters, folder, output, stitch, assembled
    SHOT# rows   one per planned shot — order, prompt, run, panel, and the
                 panels and motion the plan authored
    the folder   the tree the record names as `folder`:
                     storyboard/   the panels
                     shots/        each source clip, copied in, in cut order
                     output/       the stitched scene
                     review/       contact sheets of the board

**The row is the record.** A scene is listed by `GET /api/scenes?project=`,
ordered by `created` on the row, and its folder is named by `folder` rather
than derived from any label — so a rename touches one field, not a tree.

**Every image a scene holds is a node id.** Panels, handoff frames, the copied
shots and the cut itself. A key is invalidated by any rename of the file it
names; a node id is not.

THE WORD "SHOT"
---------------
A scene is made of **shots**, and a shot here is one run's output — the unit a
scene is cut from. Note the term is loaded elsewhere: a Kling
`multi_prompt` cut is a shot *inside* one generation, and the `studio-media-shot`
skill produces a whole still-then-clip chain. The nesting is
generation cut ⊂ shot ⊂ scene ⊂ movie.

WHY SHOTS ARE COPIED IN
-----------------------
`shots/` holds a copy of each clip as it was at cut time, so a scene stays
playable and re-stitchable even as its runs accumulate around it. The shot row
records the originating run beside the copied node, so lineage is not lost by
copying — it names both.

The copy is real — two blobs, two independent lifetimes — because the
alternative is worse: a second node pointing at one blob is copy-on-write, and
the API's delete route destroys the shared bytes when either row goes.

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

Nothing is replaced, so nothing depends on object versioning here, and dev
(which has none — `infra/modules/dev_storage/main.tf` says why) and prod
behave identically. Versioning still matters in prod for everything a DELETE
touches — it is what makes every erasure the API can perform a recoverable
tombstone.

STITCHING IS THE SERVICE'S
--------------------------
`assemble` resolves each shot to a video node, enqueues **one render job** and
waits for it. The worker downloads, copies each shot into `shots/`, stitches,
uploads the cut and records it on the scene — the last of those because a cut
that reached the bucket and never reached the record is a failure nobody can
see.

Two things stay true:

* **The joining rules are shared with a movie.** `backend/studio_core/media/ffmpeg.py`
  is the same layer `movies` goes through, so a scene and a movie join their
  inputs identically: stream-copy when everything already agrees, re-encode to
  the first input's geometry when it does not — **and say so on the record**.
  That last clause is the one thing that must never be lost in a port: a worker
  that re-encoded silently would be a quality regression nobody could see.
* **Resolution stays here.** `latest`, `#N`, "this run has three clips", "this
  shot has not been rendered" are refusals with an action in them, and a person
  should read them before a job is queued rather than after one fails.

CLI
---
    studio scenes new <project> --name <name> --from-json plan.json
    studio scenes plan <project>/<name>
    studio scenes sheet <project>/<name>            # the board, as one image
    studio scenes handoff <project>/<name> --shot N
    studio scenes assemble <project>/<name>
    studio scenes list <project>
    studio scenes show <project>/latest
    studio scenes outputs <project>/latest --presign

The two that spend money — rendering the panels and rendering a shot — live
beside the submit lifecycle they drive, not here.
"""
from __future__ import annotations

import json
import sys

import click

from studio_pipeline.adapters import api, entities, store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
from studio_pipeline import errors  # noqa: E402
from studio_pipeline.domain import frames as FRAMES  # noqa: E402  — the pool and the grab
from studio_pipeline.domain import paths as P  # noqa: E402  — the name lookup
from studio_pipeline.domain import renders as RENDER  # noqa: E402  — the encode lives there now
from studio_pipeline.domain import projects as PROJECTS  # noqa: E402
from studio_pipeline.domain import (
    runs as R,  # noqa: E402  — the run store; scenes are built from its records
)
from studio_pipeline.domain import (
    storyboard as SB,  # noqa: E402  — the plan a scene is built FROM
)

# What a scene is cut from. Shared with the run store rather than restated, so
# a new container format is legal in both places at once.
VIDEO_EXT = R.VID_EXTS

#: Folders inside a scene's own folder. Convention, resolved by name and created
#: if absent — the scene record names one node (`folder`) and no map of these.
#:
#: **`shots/` is not here, and its absence is the point.** It holds the per-shot
#: copies an assemble leaves behind, and an assemble is a job on the render queue
#: now — `services/render.py` names that folder and creates it. A constant kept
#: on this side would be a second spelling of a name this package never writes,
#: and the two could disagree with nothing to notice.
OUTPUT_FOLDER = "output"
REVIEW_FOLDER = "review"
STORYBOARD_FOLDER = "storyboard"


# ── addressing ──────────────────────────────────────────────────────────────

def resolve_scene(ref: str, default_project: str | None = None) -> dict:
    """'<project>/<name>' | '<project>/latest' | '<name>' | 'scene-<uuid>' -> the RECORD.

    Returns the **record**, not a `(project, id)` pair, exactly as
    `runs.resolve_run` does and for the same reason: every caller went straight
    on to read the scene, and a pair meant a second round trip plus two more
    strings to keep in step. It is also the sceneref resolver `movies.py` uses —
    a movie addresses its scenes the way a scene addresses its runs.

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


def scene_shots(record: dict) -> list[dict]:
    """A scene's shots, in `order`. The `SHOT#` rows the API returns with it.

    **`n` is derived here, not stored.** It is the shot's 1-based position, which
    `order` already decides — storing it would be a second answer to one question
    and would go stale the first time a plan was reordered. `storyboard.normalise`
    sets it while building a plan from JSON, and everything downstream (`--shot 3`,
    the handoff hint, panel labels) reads it; a scene read back from the API had
    never been through `normalise`, so those rows arrived without it and the
    first thing to reach for one raised `KeyError: 'n'`.
    """
    shots = sorted(record.get("shots") or [], key=lambda s: s.get("order") or 0)
    return [{**shot, "n": i} for i, shot in enumerate(shots, 1)]


def scene_output_node(record: dict) -> str | None:
    """The node id of the stitched cut, or None while the scene is only planned."""
    return (record.get("output") or {}).get("node")


def is_assembled(record: dict) -> bool:
    """Whether this scene has been cut, as opposed to merely planned."""
    return SB.is_assembled(record)


# ── the scene's folders ─────────────────────────────────────────────────────

def scene_folder(record: dict, *names: str) -> str:
    """A folder inside the scene's own folder, created if it is absent.

    The record names one node and no map of blessed folder names, so these are
    resolved by name at write time and made when missing — the self-healing the
    spec's layout section describes. Renaming `shots/` strands nothing: every
    shot row names its copied node by id.
    """
    return store.folder_path(record["folder"], *names)["id"]


def save_shots(record: dict, shots: list[dict]) -> dict:
    """Write the shot rows and refresh the scene's derived status.

    `PUT /api/scenes/<id>/shots` **merges by shot id** rather than replacing, so
    a plan revision never orphans a panel or a run somebody already paid for.
    The merge is the API's, not a check-then-write on this side.

    **`status` is the API's, on both halves.** A status derived on one client
    and stored goes stale as soon as anything else writes a shot;
    `PATCH /api/scenes/<id>/shots` derives both `shot_status` and
    `scene_status`, and the response carries them.
    """
    updated = entities.put_shots(record["id"], shots)
    # `with_project` re-derives the display fields the API does not return.
    # Without it a record that came back from a write has no `label`, and the
    # next thing to print one — a handoff hint, a refusal naming the scene —
    # raises `KeyError` on a path nothing exercised until a shot was saved and
    # then read in the same breath.
    return with_project({**record, **updated})


# ── starting a scene ────────────────────────────────────────────────────────

def new_scene(project: dict, name: str, plan_path: str | None,
              force: bool = False) -> dict:
    """Ingest a plan into a scene row and its shot rows. Nothing renders, nothing bills.

    Re-ingesting is how a plan is revised, and it must not orphan work already
    paid for — so `--force` sends the revision to `PUT /api/scenes/<id>/shots`,
    which merges by shot id server-side — panels included, since the panel-level
    merge moved there too. Nothing is carried across by hand here any more.
    """
    name = SB.check_scene_name(name)
    plan = SB.load_plan(plan_path) if plan_path else {"shots": []}

    # **The plan is sent as authored.** Normalising, validating and deriving
    # status are the API's, so a plan editor in the SPA gets the same treatment
    # a JSON file does. What stays here is the ingest-only warning below: the API
    # deliberately does not refuse a shot with no words in it — sketching beats
    # before writing prompts is authoring — but somebody who just handed over a
    # file they called finished wants to hear about it.
    shots = list(plan.get("shots") or [])
    envelope = {
        "name": name,
        "setting": plan.get("setting") or "",
        "defaults": plan.get("defaults") or {},
        "logline": plan.get("logline") or "",
        "characters": sorted(plan.get("characters") or []),
        "version": SB.VERSION,
    }
    if plan_path:
        _warn_unrenderable(shots)

    existing = next((s for s in list_scenes(project) if s.get("name") == name), None)
    if existing:
        if not force:
            die(f"{project['name']}/{name} already exists "
                f"({existing.get('status', 'unknown')}).\n"
                f"       Revising a scene means re-ingesting it: pass --force, and "
                f"every run, panel and cut it already has is carried across.")
        record = entities.get_scene(existing["id"])
        entities.patch_scene(record["id"], **envelope)
        return save_shots(record, shots)

    try:
        record = entities.create_scene(
            project=project["id"], name=name,
            shots=shots, setting=envelope["setting"], defaults=envelope["defaults"])
    except api.Conflict as exc:
        die(str(exc))
    entities.patch_scene(record["id"], logline=envelope["logline"],
                         characters=envelope["characters"], version=envelope["version"])
    return with_project(entities.get_scene(record["id"]))


def _warn_unrenderable(shots: list[dict]) -> None:
    """Say which shots have no words in them. **A warning, never a refusal.**

    The API deliberately does not refuse these: a shot with a beat and no
    prompt is a plan in progress, and refusing it would reject a plan editor's
    first save. At ingest it is nearly always a
    typo, so it is worth saying — and worth saying without stopping, because
    ingesting a plan you intend to finish is also normal.
    """
    for i, shot in enumerate(shots, 1):
        where = shot.get("id") or f"shot-{i:02d}"
        if (shot.get("panels") or (shot.get("motion") or {}).get("prompt")
                or (shot.get("prompt") or "").strip()):
            continue
        print(f"warning: {where} has nothing to render from — no panel, no "
              f"motion prompt, and no prompt.", file=sys.stderr)


def shot_video_node(shot: dict, project: str) -> str | None:
    """The NODE ID of the video a shot rendered, resolved from its run if unrecorded."""
    if shot.get("node"):
        return shot["node"]
    if not shot.get("run"):
        return None
    nodes = R.resolve_output_nodes(shot.get("runref") or shot["run"],
                                   default_project=project, kinds=VIDEO_EXT)
    if len(nodes) > 1:
        die(f"shot {shot.get('id') or shot.get('n')}: its run has {len(nodes)} videos; "
            f"record which one by appending #N to the shot's runref")
    return nodes[0]


# ── assembling ──────────────────────────────────────────────────────────────

def assemble(record: dict, refs: tuple[str, ...] = (),
             dest_dir: str | None = None) -> dict:
    """Resolve every shot to a clip, ask the service to cut them, record the cut.

    Two ways in, and they are the same code path. Normally the shots come from
    the scene's own plan, each one already rendered. `--shot <runref>` appends
    runs directly instead, which is what makes the pre-storyboard one-liner —
    "just stitch these three runs" — still a one-liner: a scene with no plan plus
    a list of runrefs is exactly the old behaviour.

    **The encode is a render job now.** This resolves, enqueues one job and waits;
    the worker downloads each clip, copies it into `shots/`, stitches, uploads the
    cut and writes `output`, `stitch`, `cuts` and `assembled` onto the scene. What
    stays here is every refusal a person can act on — an unrendered shot, an
    ambiguous runref — because those belong in front of the person and not at the
    far end of a queue.

    The bytes never pass through this machine: a four-shot 1080p scene is
    roughly a gigabyte, which no terminal should move to produce a file that
    then goes back up.
    """
    project = record["project"]
    shots = list(scene_shots(record))
    characters = set(record.get("characters") or [])

    for ref in refs:
        run = R.resolve_run(ref, default_project=project)
        nodes = R.resolve_output_nodes(ref, default_project=project, kinds=VIDEO_EXT)
        characters.update(run.get("characters") or [])
        n = len(shots) + 1
        shots.append({"n": n, "id": f"shot-{n:02d}", "runref": ref,
                      "run": run["id"], "node": RENDER.one_video(nodes, ref)})

    if not shots:
        die(f"{record['name']} has no shots — plan some, or pass --shot <runref>")

    unrendered = [s.get("id") or f"shot {s.get('n')}" for s in shots if not s.get("run")]
    if unrendered:
        die(f"{len(unrendered)} shot(s) have not been rendered: {', '.join(unrendered)}\n"
            f"       studio scenes render {record['name']} --shot <n>")

    print(f"scene {record['name']}  ({record['id']})")
    parts = []
    for n, shot in enumerate(shots, 1):
        # Resolved HERE, not in the worker. A shot that recorded no node has to
        # be looked up through its run, and a run with three clips is a question
        # for a person — `one_video` is where that refusal lives.
        parts.append(RENDER.part(shot_video_node(shot, project),
                                 run=shot.get("run"), shot=shot.get("id")))
        print(f"  shot {n}: {shot['run']}")

    result = RENDER.submit("assemble", {"target": record["id"], "parts": parts,
                                        "characters": sorted(characters)},
                           what="the cut")

    superseded = scene_output_node(record)
    # Re-read rather than restated: the worker wrote the output, the stitch report
    # and the shot rows, so the record it produced is the current one and anything
    # this process asserted would be a second opinion.
    record = with_project(entities.get_scene(record["id"]))

    if result.get("re_encoded"):
        # **Said out loud, because it is a quality fact about the file.** The
        # stitcher normalises to the first input's geometry when the shots
        # disagree, and the report on the record says so — but a person watching
        # a terminal should not have to go and read the record to find out.
        print(f"  ({result['stitch']['method']})")
    if superseded:
        print(f"  (the previous cut is kept — {superseded} — and listed under "
              f"`cuts` on the scene)")

    if dest_dir:
        record = {**record, "local": RENDER.fetch(result["output"], dest_dir)}
    return record


# ── carrying a shot forward ─────────────────────────────────────────────────

def handoff(record: dict, n: int, from_run: str | None = None) -> dict:
    """Take the previous shot's last frame and hand it to shot N.

    Two things, and the second is the point: the frame goes into the project's
    input pool, and is written onto shot N as the frame it opens on. There is no
    third record — `storyboard.scene_frames` reads the sequence back off the
    shot rows, so the scene's own frames cannot drift from the scene.

    **The grab is a render job and the patch is not.** Pulling a frame needs
    ffmpeg and a clip; writing `opens_on` onto a shot is one `PATCH` on a node id.
    Keeping the second here means the worker's contract stays "one node out" and
    nothing about the plan is decided inside an encoder.

    It is one `PATCH /api/scenes/<id>/shots/<shot_id>`, not a rewrite of the plan.
    A whole-document write was the only option while the plan was one JSON file,
    and it meant two handoffs recorded at once fought over it.
    """
    shots = scene_shots(record)
    by_n = {shot.get("n") or i: shot for i, shot in enumerate(shots, 1)}
    shot, previous = by_n.get(n), by_n.get(n - 1)
    if not shot:
        die(f"{record['name']} has no shot {n} (it has {sorted(by_n)})")
    if not previous:
        die(f"shot {n} is the first shot — there is nothing before it to hand off from")
    ref = from_run or previous.get("runref") or previous.get("run")
    if not ref:
        die(f"shot {previous.get('id')} has not been rendered, so it has no last frame\n"
            f"       studio scenes render {record['name']} --shot {n - 1}")

    run, video = FRAMES.resolve_video(ref, record["project"])
    project = PROJECTS.resolve(record["project"])
    result = RENDER.submit("frame", {
        "node": video,
        "from_end": 0.2,
        "dest": store.ensure_child_folder(project["root"], P.INPUT_FOLDER)["id"],
        "name": f"{run['id']}_last.png",
    }, what="the handoff frame")
    node = result["frame"]["node"]

    entities.patch_shot(record["id"], shot["id"], continues=True,
                        opens_on={"node": node, "from_run": run["id"]})
    # Re-read rather than restated: `PATCH /api/scenes/<id>/shots/<id>` derives
    # the scene's status from the shot it just wrote, so the record that comes
    # back is already current.
    record = with_project(entities.get_scene(record["id"]))

    print(node)
    print(f"shot {n} ({shot.get('id')}) now opens on the last frame of "
          f"{previous.get('id')}")
    # Served on the scene now — derived from the plan rather than from a
    # `chains/<scene>.json` kept in step by hand.
    print(f"the scene's own frames are now: "
          f"{len(record.get('frames') or [])}", flush=True)
    return record


# ── reading the plan ────────────────────────────────────────────────────────

def plan_prompts(record: dict) -> list[str]:
    """Every word the plan will send, laid out to be read.

    The prompts are on the shot rows and are therefore already stored, but a raw
    record is not a readable thing — a prompt is prose and wants to be read as
    prose before it is paid for.
    """
    out = []
    if record.get("setting"):
        out += ["", "=" * 70, "SETTING — prepended to every PANEL prompt", "=" * 70,
                record["setting"]]
    for shot in scene_shots(record):
        roles = SB.panel_roles(shot)
        out += ["", "=" * 70,
                f"{shot.get('id')}  —  {shot.get('beat', '')}".rstrip(),
                "=" * 70]
        for panel, role in zip(shot.get("panels") or [], roles):
            if SB.is_supplied(panel):
                out += [f"--- panel {panel['n']} [{role}] — supplied image, no prompt",
                        f"    {panel.get('node')}"]
                continue
            out += [f"--- panel {panel['n']} [{role}]  ({panel.get('model')})",
                    panel.get("prompt") or ""]
        motion = shot.get("motion") or {}
        out += [f"--- motion  ({motion.get('model')}, {motion.get('duration')}s)",
                motion.get("prompt") or ""]
    return out


def plan_table(record: dict) -> list[str]:
    """The plan as lines you can scan — `show` stays raw JSON for machines."""
    out = [f"{record['name']}  ({record['id']})  [{record.get('status', '?')}]"]
    if record.get("logline"):
        out.append(f"  {record['logline']}")
    for shot in scene_shots(record):
        roles = SB.panel_roles(shot)
        panels = shot.get("panels") or []
        bits = []
        for panel, role in zip(panels, roles):
            mark = "*" if panel.get("node") else "-"
            stale = "!" if panel.get("stale") else ""
            bits.append(f"{mark}p{panel['n']}[{role}]{stale}")
        motion = shot.get("motion") or {}
        out.append(
            f"  {shot.get('id', '?'):<10} {shot.get('status', '?'):<9} "
            f"{motion.get('model', '?')} {motion.get('duration', '?')}s  "
            f"{' '.join(bits) or '(no panels)'}  {shot.get('beat', '')}".rstrip())
    if any(p.get("stale") for s in scene_shots(record) for p in s.get("panels") or []):
        out.append("  ! = the panel in the library predates its prompt")
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────

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
@click.option("--name", required=True)
@errors.reports(SB.PlanError, P.PathError, api.ApiError)
def do_new(project, force, from_json, part, shot, name):
    """Start a scene from a plan."""
    # `--shot`/`--part` belong to `scenes assemble`. They are kept visible to
    # the parser here and answered with a redirect, because a silent "unknown
    # option" on a command that exists reads as a broken install.
    if shot or part:
        die("`scenes new` starts a scene from a plan; it no longer assembles one.\n"
            f"       studio scenes new {project} --name {name}\n"
            f"       studio scenes assemble {project}/{name} "
            + " ".join(f"--shot {r}" for r in (*shot, *part)))
    record = new_scene(PROJECTS.require_project(project), name, from_json, force)
    print("\n".join(plan_table(record)))
    print(f"\nnext: studio scenes check {project}/{record['name']}")


@main.command("assemble")
@click.argument("ref", required=True)
@click.option("--dest", help="also keep the stitched file locally")
@click.option("--project")
@click.option("--shot", multiple=True,
              help=("a run output to append, in cut order. Repeatable. Accepts "
                    "<project>/<name>, a run id, a unique name fragment, or #N."))
@errors.reports(R.RunError, api.ApiError, RENDER.RenderError)
def do_assemble(ref, dest, project, shot):
    """Cut a scene's rendered shots into one continuous take."""
    record = assemble(resolve_scene(ref, project), shot, dest)
    print(json.dumps({"scene": record["id"], "name": record.get("name"),
                      "output": record.get("output"),
                      "stitch": record.get("stitch")}, indent=2))


@main.command("handoff")
@click.argument("ref", required=True)
@click.option("--from-run", "from_run",
              help="the run to take the frame from (default: the previous shot's)")
@click.option("--project")
@click.option("--shot", type=int, required=True,
              help="the shot that should OPEN on this frame")
@errors.reports(R.RunError, api.ApiError, RENDER.RenderError)
def do_handoff(ref, from_run, project, shot):
    """Carry the previous shot's last frame into the next one."""
    handoff(resolve_scene(ref, project), shot, from_run)


@main.command("plan")
@click.argument("ref", required=True)
@click.option("--project")
@click.option("--prompts", is_flag=True,
              help="also print every prompt in full — what each panel and each shot says")
@errors.reports(api.ApiError)
def do_plan(ref, project, prompts):
    """A scene's plan, as a table rather than as JSON."""
    record = resolve_scene(ref, project)
    print("\n".join(plan_table(record)))
    if prompts:
        print("\n".join(plan_prompts(record)))


@main.command("sheet")
@click.argument("ref", required=True)
@click.option("--cell", type=int, default=320)
@click.option("--cols", type=int, default=4)
@click.option("--out", help="where to write the sheet (default: a temp directory)")
@click.option("--project")
@errors.reports(api.ApiError, RENDER.RenderError)
def do_sheet(ref, cols, cell, out, project):
    """The whole board as one captioned contact sheet.

    A board only means anything looked at. This is also the only way an agent
    can read its own storyboard, which is why `frames grid` exists for clips.
    """
    record = resolve_scene(ref, project)
    captions = SB.sheet_captions(record)
    if not captions:
        die(f"{record['name']} has no panels yet — studio scenes board "
            f"{record['id']}")

    # **Captions are given, so the order is authoritative.** A board's tiles read
    # in shot order and say which panel each one is; natural-sorting them by
    # filename would renumber the thing the sheet exists to communicate.
    result = RENDER.submit("sheet", {
        "parts": [RENDER.part(node, caption=caption) for node, caption in captions],
        "cols": cols, "cell": cell,
        "dest": scene_folder(record, REVIEW_FOLDER),
        "name": "board.png",
    }, what="the board")
    # The board is the thing someone looks at to judge the scene, and it is in
    # `review/` whether or not `--out` was given — leaving it only on local disk
    # would mean only whoever ran the command could see it.
    print(result["sheet"]["node"])
    if out:
        print(f"  (local copy: {RENDER.fetch(result['sheet'], out)})")


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
    """One scene's record, with its shot rows."""
    print(json.dumps(resolve_scene(ref, project), indent=2))


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
