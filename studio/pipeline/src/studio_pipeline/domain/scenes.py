"""`studio scenes` — the SCENE store: a piece planned, shot, and cut.

A **run** is one submission to a model (see `runs.py`). A **scene** is an ordered
sequence of run outputs stitched into a single continuous video — and, since
storyboards, the plan those runs are made from.

WHAT A SCENE IS NOW
-------------------
A **row**, `scene-<uuid>`, addressed by id and labelled by a slug:

    the row      id, project, slug, title, setting, defaults, status,
                 characters, folder, output, stitch, assembled
    SHOT# rows   one per planned shot — order, prompt, run, panel, and the
                 panels and motion the plan authored
    the folder   the tree the record names as `folder`:
                     storyboard/   the panels
                     shots/        each source clip, copied in, in cut order
                     output/       the stitched scene
                     review/       contact sheets of the board

**`scene.json` is gone.** It was the plan *and* the record in one document in the
bucket, which meant nothing could query a scene, `latest` had to be found by
reading every manifest in the project, and the slug in the folder name was the
primary key — so a rename was a tree rewrite. All three go together: a scene is
listed by `GET /api/scenes?project=`, ordered by `created` on the row, and its
folder is named by `folder` rather than derived from its slug.

**Every image a scene holds is a node id.** Panels, handoff frames, the copied
shots and the cut itself. A key was invalidated by any rename of the file it
named, which is what left records pointing at images that no longer existed.

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
playable and re-stitchable even as its runs accumulate around it. The shot row
records the originating run beside the copied node, so lineage is not lost by
copying — it names both.

That copy is a download plus an upload, so every shot's bytes travel through
this process, and for a scene they are video. It is accepted for the reason the
alternative is worse: a second node pointing at one blob is copy-on-write
(#334), and the API's delete route destroys the shared bytes when either row
goes. So the copy is real — two blobs, two independent lifetimes.

RE-CUTTING KEEPS THE ONE BEFORE IT
---------------------------------
Each cut is its own node: the first is `<slug>.mp4` and later ones take a
suffix, `<slug>-2.mp4` and up. `output` names the newest and `cuts` lists the
rest, newest first.

**This reverses an earlier decision and is worth saying why.** The cut used to
replace the file in `output/`, so the folder always showed current state instead
of accumulating cuts nobody prunes, and a superseded cut survived as an S3
object version. That is genuinely recoverable and it is not *visible*: an object
version has no node, so nothing lists it, nothing draws it and nothing links to
it. A person who re-cut a scene after re-rendering one shot could not put the
two takes side by side, which is the thing re-cutting is for.

The old argument was about tidiness and the new one is about being able to look
at your own work, so the accumulation is accepted. Old cuts are deletable like
any other node.

**What makes that recoverable is true of PROD only.** The prod bucket versions
every object and grants no `s3:DeleteObjectVersion`, so a superseded cut is
still there to restore. A per-machine dev stack has no versioning, deliberately
— `infra/modules/dev_storage/main.tf` says why: the recovery there is a re-seed
via `dev-aws-reset.sh`, and version history would only slow the teardown and
bill for bytes nobody restores. Against dev, a re-cut destroys the previous one.

STITCHING STAYS LOCAL, AND THAT IS DELIBERATE
---------------------------------------------
`ffmpeg` ships in this wheel (`imageio-ffmpeg`) and the Lambda behind the API
has none, so `assemble` downloads each rendered shot, stitches here, uploads the
result through the URL `POST /api/scenes/<id>/output` signs, and then `PATCH`es
the record with the cut. **The API owns the record; it does not own the encode.**
Moving the encode server-side would mean putting a video toolchain in a function
whose request limit is 6 MB, to save a hop that has to happen anyway because the
shots are being copied in regardless.

`adapters/ffmpeg.py` is the same layer `movies.py` uses, so a scene and a movie
join their inputs by identical rules: stream-copy when everything already
agrees, re-encode to the first input's geometry (and say so on the record) when
it does not.

CLI
---
    studio scenes new <project> --slug <slug> --from-json plan.json
    studio scenes plan <project>/<slug>
    studio scenes sheet <project>/<slug>            # the board, as one image
    studio scenes handoff <project>/<slug> --shot N
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
import sys
import tempfile

import click

from studio_pipeline.adapters.ffmpeg import (  # noqa: E402  — shared with movies.py and frames.py
    grab,
    probe,
    stitch,
)
from studio_pipeline.adapters import api, entities, store  # noqa: E402
from studio_pipeline.errors import die  # noqa: E402
from studio_pipeline import errors  # noqa: E402
from studio_pipeline.domain import contact_sheet  # noqa: E402  — a board is read by looking
from studio_pipeline.domain import frames as FRAMES  # noqa: E402  — the pool and the grab
from studio_pipeline.domain import paths as P  # noqa: E402  — the slug rule
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
SHOTS_FOLDER = "shots"
OUTPUT_FOLDER = "output"
REVIEW_FOLDER = "review"
STORYBOARD_FOLDER = "storyboard"


# ── addressing ──────────────────────────────────────────────────────────────

def resolve_scene(ref: str, default_project: str | None = None) -> dict:
    """'<project>/<slug>' | '<project>/latest' | '<slug>' | 'scene-<uuid>' -> the RECORD.

    Returns the **record**, not a `(project, id)` pair, exactly as
    `runs.resolve_run` does and for the same reason: every caller went straight
    on to read the scene, and a pair meant a second round trip plus two more
    strings to keep in step. It is also the sceneref resolver `movies.py` uses —
    a movie addresses its scenes the way a scene addresses its runs.

    An id resolves directly and needs no project, which is what makes a record
    that stored a scene id self-sufficient.

    **`latest` is now `created` on the row.** It used to read every manifest in
    the project and take the newest, because a lexical sort over folder names
    put every slug after every timestamp and `latest` would otherwise have
    quietly meant "alphabetically last" — the exact caller that would have got
    it wrong being `movies new --scene <project>/latest`. The row carries the
    timestamp, so there is nothing left to re-derive.
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
        die(f"cannot resolve scene {ref!r}: no project given (use <project>/<slug>)")

    record = PROJECTS.require_project(project)
    found = list_scenes(record)
    if not found:
        die(f"project {record['slug']} has no scenes")
    if sid in ("latest", "last"):
        return with_project(entities.get_scene(found[0]["id"]))
    # `.get`, not `[...]`: the listing projection did not carry `slug` until the
    # API started writing it, so every row created before then has none. Reading
    # it as a required key turned "this scene predates the fix" into a traceback
    # on every command that addresses a scene by name.
    hits = [s for s in found if s.get("slug") == sid]
    if not hits:
        hits = [s for s in found if sid in (s.get("slug") or "")]
    if len(hits) == 1:
        return with_project(entities.get_scene(hits[0]["id"]))
    if not hits:
        die(f"no scene matching {sid!r} in project {record['slug']}")
    die(f"{sid!r} is ambiguous in project {record['slug']}: "
        + ", ".join(f"{s['id']} ({s.get('slug') or '-'})" for s in hits[:5]))


def with_project(record: dict) -> dict:
    """A scene record carrying `project_slug` and `label`, for printing.

    **Two display fields, added once, because a record holds ids and a person
    reads names.** The old manifest carried `scene: "<project>/<slug>"` as a
    stored string, which is exactly the coupling the entity model removes — it
    went stale the moment either was renamed. These are derived on read instead,
    so they are always current and nothing writes them anywhere.

    One extra `GET /api/projects/<id>` per resolve, and only when a caller
    actually needs to print something. `resolve_scene` does it because every one
    of its callers does.
    """
    if record.get("project_slug"):
        return record
    slug = PROJECTS.resolve(record["project"])["slug"]
    return {**record, "project_slug": slug, "label": f"{slug}/{record['slug']}"}


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
    the handoff hint, panel slugs) reads it; a scene read back from the API had
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
    That merge used to be this module's job, done against a document it had just
    read — a check-then-write with a gap in it.

    **`status` is the API's now, on both halves.** This used to stamp
    `shot_status` onto every shot before sending and then PATCH the scene with
    `scene_status` afterwards — two derivations run on one client and stored, so
    anything else that wrote a shot left them stale and the SPA drew whatever the
    row said. `PATCH /api/scenes/<id>/shots` derives both, and the response
    carries them.
    """
    updated = entities.put_shots(record["id"], shots)
    # `with_project` re-derives the display fields the API does not return.
    # Without it a record that came back from a write has no `label`, and the
    # next thing to print one — a handoff hint, a refusal naming the scene —
    # raises `KeyError` on a path nothing exercised until a shot was saved and
    # then read in the same breath.
    return with_project({**record, **updated})


# ── starting a scene ────────────────────────────────────────────────────────

def new_scene(project: dict, slug: str, plan_path: str | None,
              title: str = "", force: bool = False) -> dict:
    """Ingest a plan into a scene row and its shot rows. Nothing renders, nothing bills.

    Re-ingesting is how a plan is revised, and it must not orphan work already
    paid for — so `--force` sends the revision to `PUT /api/scenes/<id>/shots`,
    which merges by shot id server-side — panels included, since the panel-level
    merge moved there too. Nothing is carried across by hand here any more.
    """
    SB.check_scene_slug(slug)
    plan = SB.load_plan(plan_path) if plan_path else {"shots": []}
    if title:
        plan["title"] = title

    # **The plan is sent as authored.** Normalising, validating and deriving
    # status are the API's, so a plan editor in the SPA gets the same treatment
    # a JSON file does. What stays here is the ingest-only warning below: the API
    # deliberately does not refuse a shot with no words in it — sketching beats
    # before writing prompts is authoring — but somebody who just handed over a
    # file they called finished wants to hear about it.
    shots = list(plan.get("shots") or [])
    envelope = {
        "title": plan.get("title") or slug,
        "setting": plan.get("setting") or "",
        "defaults": plan.get("defaults") or {},
        "logline": plan.get("logline") or "",
        "characters": sorted(plan.get("characters") or []),
        "version": SB.VERSION,
    }
    if plan_path:
        _warn_unrenderable(shots)

    existing = next((s for s in list_scenes(project) if s.get("slug") == slug), None)
    if existing:
        if not force:
            die(f"{project['slug']}/{slug} already exists "
                f"({existing.get('status', 'unknown')}).\n"
                f"       Revising a scene means re-ingesting it: pass --force, and "
                f"every run, panel and cut it already has is carried across.")
        record = entities.get_scene(existing["id"])
        entities.patch_scene(record["id"], **envelope)
        return save_shots(record, shots)

    try:
        record = entities.create_scene(
            project=project["id"], slug=slug, title=envelope["title"],
            shots=shots, setting=envelope["setting"], defaults=envelope["defaults"])
    except api.Conflict as exc:
        die(str(exc))
    entities.patch_scene(record["id"], logline=envelope["logline"],
                         characters=envelope["characters"], version=envelope["version"])
    return with_project(entities.get_scene(record["id"]))


def _warn_unrenderable(shots: list[dict]) -> None:
    """Say which shots have no words in them. **A warning, never a refusal.**

    `storyboard.validate` used to refuse these, and the API deliberately does
    not: a shot with a beat and no prompt is a plan in progress, and refusing it
    would reject a plan editor's first save. At ingest it is nearly always a
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
    """Copy each rendered shot in, stitch them LOCALLY, and record the cut.

    Two ways in, and they are the same code path. Normally the shots come from
    the scene's own plan, each one already rendered. `--shot <runref>` appends
    runs directly instead, which is what makes the pre-storyboard one-liner —
    "just stitch these three runs" — still a one-liner: a scene with no plan
    plus a list of runrefs is exactly the old behaviour.

    **The encode is here and not in the API.** `ffmpeg` ships in this wheel and
    the Lambda has none, so the bytes come down, `adapters/ffmpeg` joins them,
    and the result goes up through the URL `POST /api/scenes/<id>/output` signs.
    The API then owns the record — `PATCH` writes the output node, the stitch
    report and the assembly time — and owns nothing about how the file was made.
    """
    project = record["project"]
    shots = list(scene_shots(record))
    characters = set(record.get("characters") or [])

    for ref in refs:
        run = R.resolve_run(ref, default_project=project)
        nodes = R.resolve_output_nodes(ref, default_project=project, kinds=VIDEO_EXT)
        if len(nodes) > 1:
            die(f"{ref}: {len(nodes)} videos; append #N to pick one")
        characters.update(run.get("characters") or [])
        n = len(shots) + 1
        shots.append({"n": n, "id": f"shot-{n:02d}", "runref": ref,
                      "run": run["id"], "node": nodes[0]})

    if not shots:
        die(f"{record['slug']} has no shots — plan some, or pass --shot <runref>")

    unrendered = [s.get("id") or f"shot {s.get('n')}" for s in shots if not s.get("run")]
    if unrendered:
        die(f"{len(unrendered)} shot(s) have not been rendered: {', '.join(unrendered)}\n"
            f"       studio scenes render {record['slug']} --shot <n>")

    slug = record.get("slug")
    print(f"scene {record['slug']}  ({record['id']})")

    tmp = tempfile.mkdtemp(prefix="scene-")
    shots_folder = scene_folder(record, SHOTS_FOLDER)
    local: list[str] = []
    for n, shot in enumerate(shots, 1):
        src = shot_video_node(shot, project)
        name = store.node(src).get("name") or f"{src}.mp4"
        ext = os.path.splitext(name)[1] or ".mp4"
        lp = os.path.join(tmp, f"shot-{n:02d}{ext}")
        store.download_node(src, pathlib.Path(lp))
        local.append(lp)
        shot["n"] = n
        shot["node"] = src
        # A read plus a write, where this was a server-side `CopyObject`. The
        # bytes travel through this process and for a scene they are video —
        # accepted because the alternative is worse: a second node pointing at
        # one blob is copy-on-write (#334), and the API's delete route destroys
        # the shared bytes when either row goes. The file is already local from
        # the download above, so the extra cost is one PUT per shot.
        copied = store.upload_into(
            shots_folder, f"shot-{n:02d}{ext}", pathlib.Path(lp),
            content_type=mimetypes.guess_type(lp)[0] or "application/octet-stream")
        shot["shot_node"] = copied["id"]
        print(f"  shot {n}: {shot['run']}")

    out_local = os.path.join(tmp, f"{R.slugify(slug)}.mp4")
    info = stitch(local, out_local, label="shots")
    for shot, pr in zip(shots, info.pop("probes")):
        shot["duration"] = pr["duration"]

    superseded = scene_output_node(record)
    # A NEW node per cut, so the one before it stays reachable. Numbered from
    # what the record already holds rather than from the folder, because the
    # record is what `cuts` is read off and a stray file in the folder must not
    # be able to renumber a history that does not include it.
    take = len(record.get("cuts") or []) + (1 if superseded else 0) + 1
    name = f"{R.slugify(slug)}.mp4" if take == 1 else f"{R.slugify(slug)}-{take}.mp4"
    signed = entities.scene_output(record["id"], name,
                                   os.path.getsize(out_local), "video/mp4")
    store.upload_to_url(signed, pathlib.Path(out_local))

    entities.patch_scene(record["id"], characters=sorted(characters), stitch=info,
                         output={"node": signed["node"], **probe(out_local)},
                         assembled=R._now())
    record = save_shots(entities.get_scene(record["id"]), shots)

    if superseded:
        print(f"  (the previous cut is kept — {superseded} — and listed under "
              f"`cuts` on the scene)")

    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        keep = os.path.join(dest_dir, os.path.basename(out_local))
        os.replace(out_local, keep)
        record = {**record, "local": keep}
    return record


# ── carrying a shot forward ─────────────────────────────────────────────────

def handoff(record: dict, n: int, from_run: str | None = None) -> dict:
    """Take the previous shot's last frame and hand it to shot N.

    Two things, and the second is the point: the frame goes into the project's
    input pool, and is written onto shot N as the frame it opens on. There is no
    third record — `storyboard.scene_frames` reads the sequence back off the
    shot rows, so the scene's own frames cannot drift from the scene.

    It is one `PATCH /api/scenes/<id>/shots/<shot_id>`, not a rewrite of the
    plan. A whole-document write was the only option while the plan was one
    JSON file, and it meant two handoffs recorded at once fought over it.
    """
    shots = scene_shots(record)
    by_n = {shot.get("n") or i: shot for i, shot in enumerate(shots, 1)}
    shot, previous = by_n.get(n), by_n.get(n - 1)
    if not shot:
        die(f"{record['slug']} has no shot {n} (it has {sorted(by_n)})")
    if not previous:
        die(f"shot {n} is the first shot — there is nothing before it to hand off from")
    ref = from_run or previous.get("runref") or previous.get("run")
    if not ref:
        die(f"shot {previous.get('id')} has not been rendered, so it has no last frame\n"
            f"       studio scenes render {record['slug']} --shot {n - 1}")

    tmp = tempfile.mkdtemp(prefix="handoff-")
    run, src = FRAMES.fetch_video(ref, record["project"], tmp)
    local = grab(src, None, os.path.join(tmp, f"{run['id']}_last.png"), from_end=0.2)
    project = PROJECTS.resolve(record["project"])
    node = FRAMES.add_to_input_pool(project, local)

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
    # `chains/<slug>.json` kept in step by hand.
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
    out = [f"{record['slug']}  ({record['id']})  [{record.get('status', '?')}]"]
    if record.get("title"):
        out.append(f"  {record['title']}")
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
@click.option("--slug", required=True)
@click.option("--title", default="")
@errors.reports(SB.PlanError, P.PathError, api.ApiError)
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
    record = new_scene(PROJECTS.require_project(project), slug, from_json, title, force)
    print("\n".join(plan_table(record)))
    print(f"\nnext: studio scenes check {project}/{record['slug']}")


@main.command("assemble")
@click.argument("ref", required=True)
@click.option("--dest", help="also keep the stitched file locally")
@click.option("--project")
@click.option("--shot", multiple=True,
              help=("a run output to append, in cut order. Repeatable. Accepts "
                    "<project>/<slug>, a run id, a unique slug fragment, or #N."))
@errors.reports(R.RunError, api.ApiError)
def do_assemble(ref, dest, project, shot):
    """Cut a scene's rendered shots into one continuous take."""
    record = assemble(resolve_scene(ref, project), shot, dest)
    print(json.dumps({"scene": record["id"], "slug": record["slug"],
                      "output": record.get("output"),
                      "stitch": record.get("stitch")}, indent=2))


@main.command("handoff")
@click.argument("ref", required=True)
@click.option("--from-run", "from_run",
              help="the run to take the frame from (default: the previous shot's)")
@click.option("--project")
@click.option("--shot", type=int, required=True,
              help="the shot that should OPEN on this frame")
@errors.reports(R.RunError, api.ApiError)
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
@errors.reports(api.ApiError)
def do_sheet(ref, cols, cell, out, project):
    """The whole board as one captioned contact sheet.

    A board only means anything looked at. This is also the only way an agent
    can read its own storyboard, which is why `frames grid` exists for clips.
    """
    record = resolve_scene(ref, project)
    captions = SB.sheet_captions(record)
    if not captions:
        die(f"{record['slug']} has no panels yet — studio scenes board "
            f"{record['id']}")

    tmp = tempfile.mkdtemp(prefix="board-")
    paths, labels = [], []
    for node, caption in captions:
        name = store.node(node).get("name") or f"{node}.png"
        lp = os.path.join(tmp, name)
        store.download_node(node, pathlib.Path(lp))
        paths.append(lp)
        labels.append(caption)
    dest = os.path.join(out or tmp, f"{record['slug']}-board.png")
    local = contact_sheet.build(paths, dest, cols=cols, cell=cell, captions=labels)
    # The board is the thing someone looks at to judge the scene. Leaving it on
    # local disk means only whoever ran the command can see it.
    node = store.upload_into(scene_folder(record, REVIEW_FOLDER), "board.png",
                             pathlib.Path(local), content_type="image/png")
    print(node["id"])
    if out:
        print(f"  (local copy: {local})")


@main.command("list")
@click.argument("project", required=True)
@errors.reports(api.ApiError)
def do_list(project):
    """Every scene in a project, newest first."""
    found = list_scenes(PROJECTS.require_project(project))
    if not found:
        print(f"project {project} has no scenes")
    for scene in found:
        print(f"{scene['id']}  {(scene.get('slug') or '-'):<24} "
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
