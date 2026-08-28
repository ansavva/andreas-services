"""The SCENE PLAN — a storyboard, and the rules that read it.

A scene used to appear only at the end: you rendered clips, looked at them, and
`studio scenes new` stitched whatever you had. Nothing said what the scene *was*
until it was finished, so the only way to find out whether the flow worked was to
buy it. A 15-second Kling shot with audio is ~$3.36.

A **storyboard** puts the plan first. Each shot gets one or more **panels** —
stills, which cost cents — so the flow can be read before any video bills. The
panels are not thrown away afterwards: they become the images the video model
renders from.

    plan (this module)  ->  panels  ->  shots  ->  the cut

WHY THE PLAN IS DATA AND NOT A TEMPLATE
---------------------------------------
`reference_angles.yaml` is a spec that ships in the package, because every
character's reference set is the same fourteen angles. A storyboard is the
opposite: it is prose about one particular scene, and prose about a scene names
what happens in it. That cannot live in this repository (see `studio/CLAUDE.md`,
hard rule 1), so a plan is authored outside it and ingested with
`studio scenes new --from-json`.

THE PLAN IS NO LONGER A DOCUMENT
--------------------------------
It used to be stored as `scene.json` in the bucket, and this module's output was
that file. It is now a **scene row plus one `SHOT#` row per shot**, so what
`normalise` returns is the body of `POST /api/scenes` and of
`PUT /api/scenes/<id>/shots` rather than a file anybody writes.

Everything the record owns has therefore left this module: `scene`, `project`,
`created`, `updated`, `stitch`, `output` and `assembled` are the API's, and a
plan carrying its own copies would be a second truth to keep in step — the exact
failure the entity model exists to end. What is left is what an author writes
plus what can be derived from it.

This module is the plan and nothing else — no S3, no API, no models, no Click.
It loads a plan, fills in what the plan left implicit, refuses a plan that
cannot mean anything, and answers the one question the rest of the code needs:

    resolve_roles(shot)  ->  which panel is the start frame, which is the end,
                             and which merely ride along as references

ROLES, AND WHY A HANDOFF OUTRANKS A PANEL
-----------------------------------------
Panels are positional: the first is the start frame, the last the end frame, and
anything between them is a reference. A panel may say `role` outright and win.

Then continuity speaks. A shot that continues the one before it opens on that
shot's **literal last frame**, and only that frame makes the cut seamless — a
storyboard panel, however carefully composed, will differ from it in a hundred
small ways that read as a jump. So when a shot has a handoff frame, the handoff
becomes the start frame and the start *panel is demoted to a reference*, still
steering where the shot goes without breaking the join. Shot 1 has nothing before
it, so its first panel really is the start.

`"continues": false` on a shot forces the panel back — the right answer when a
shot deliberately opens on a new composition rather than continuing a movement.

THE SCENE'S OWN FRAMES ARE DERIVED, NOT STORED
----------------------------------------------
A shot's references should be the images this scene has already produced, not the
character's curated set: those were shot in another context and pull the render
toward it. That list used to live in a `chains/<slug>.json` written beside the
scene and kept in sync by hand — two records of one sequence, which is the shape
of every bug this repo has had to write a migrator for.

It is now read off the plan: shot 1's opening panel is the seed, and every later
shot's `opens_on.node` is the handoff the shot before it produced. See
`scene_frames`. `studio frames chain` still exists for a sequence with no scene
behind it, which is the only thing it was ever actually used for.

EVERY IMAGE IN A PLAN IS A NODE ID
----------------------------------
Panels, handoffs and cut shots all named S3 keys until the entity model. A key
is invalidated by any rename or move of the file it names, which is what left
sixty-nine records pointing at images that no longer existed; a node id survives
both by construction. So `panel.node`, `shot.node`, `shot.shot_node` and
`opens_on.node` are ids, and the `_key` spellings they replace are gone rather
than aliased — an alias is how two spellings of one thing drift.

NOTHING HERE KNOWS ABOUT MODELS
-------------------------------
Whether a model accepts an end frame, how many images it takes, and which formats
it rejects are registry questions, and asking them here would point the
dependency arrow the wrong way (`domain` never imports `engine`). Model-aware
validation lives beside the submit lifecycle, where the existing rules already
are — copying a cap check is how two versions of it drift apart.
"""

from __future__ import annotations

import json

from studio_pipeline.domain import paths as P

# The plan shape. Bumped when a field changes meaning, not when one is added.
# v3 is the entity model: every image is a node id, and the fields the scene
# record owns are gone from here.
VERSION = 3

#: What a panel is FOR, which is the same question as "does this bind".
#:
#: `start` and `end` are frames the model is given; `reference` steers the look
#: without fixing a frame. `sample` binds to **nothing** — it is a still that
#: shows a person what the shot should look like, so a fifteen-second render can
#: be judged before it is bought rather than after. It has to be a role rather
#: than a convention because the positional rule below would otherwise make the
#: last panel of every shot an end frame, and an end frame on Kling silently
#: drops every reference alongside it.
ROLES = ("start", "end", "reference", "sample")

#: Panel fields recorded by the tools and carried across a re-ingest.
#: `node` is the boarded image, `source_node` the run output it was copied
#: from — both node ids, where both were S3 keys.
PANEL_RECORDED = ("run", "source_node", "node", "boarded", "stale")

#: Shot fields recorded by `scenes render` / `scenes assemble`, never authored.
#: `node` is the rendered clip; `shot_node` its copy in the scene's `shots/`.
SHOT_RECORDED = ("run", "runref", "node", "shot_node", "duration", "rendered")


class PlanError(Exception):
    """A plan that cannot be stored, or cannot mean anything once stored."""


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def load_plan(path: str) -> dict:
    """Read a plan from a local JSON file, or fail saying which file is wrong."""
    try:
        with open(path) as fh:
            plan = json.load(fh)
    except FileNotFoundError:
        raise PlanError(f"no such plan file: {path}")
    except json.JSONDecodeError as exc:
        raise PlanError(f"{path} is not valid JSON:\n  {exc}")
    if not isinstance(plan, dict):
        raise PlanError(f"{path} must be a JSON object, not a {type(plan).__name__}.")
    return plan


def check_scene_slug(slug: str) -> str:
    """A scene slug: a label a person types, and the name of the scene's folder.

    **The timestamp check is gone.** This also refused anything shaped like a
    run id, because a scene folder was once `<timestamp>_<slug>` and a new scene
    named that way would have been indistinguishable from one of them. A scene
    is a row with a UUID now and its slug is an attribute of it, so there is
    nothing left for a timestamp-shaped name to collide with — the check would
    only refuse a legal name for a reason that stopped being true.
    """
    try:
        return P.check_slug(slug, "scene slug")
    except P.PathError as exc:
        raise PlanError(str(exc)) from exc


# --------------------------------------------------------------------------
# normalising — fill in what the plan left implicit
# --------------------------------------------------------------------------

def _inherit(defaults: dict, own: dict | None, *keys: str) -> dict:
    """Shot- or panel-level values over scene defaults, key by key.

    `extra` merges rather than replaces, so a shot can set one knob without
    restating the scene's whole technical block.
    """
    out = {}
    own = own or {}
    for k in keys:
        if k == "extra":
            out[k] = {**(defaults.get("extra") or {}), **(own.get("extra") or {})}
        elif own.get(k) is not None:
            out[k] = own[k]
        elif defaults.get(k) is not None:
            out[k] = defaults[k]
    return out


def normalise(plan: dict, slug: str) -> dict:
    """A plan as authored -> the body `POST /api/scenes` takes, nothing implicit.

    Numbering, ids, inherited defaults and derived status are all filled in here
    so that everything downstream reads one shape. Recorded fields (`run`,
    `node`, …) are initialised to None and are the tools' to write, never the
    author's.

    **It no longer takes a project and no longer returns a manifest.** A scene's
    project, id, timings, stitch and output are on the record and the API owns
    every one of them; returning copies here would be a second truth for a
    rename or a re-cut to leave behind.
    """
    defaults = dict(plan.get("defaults") or {})

    shots = []
    for i, raw in enumerate(plan.get("shots") or [], 1):
        if not isinstance(raw, dict):
            raise PlanError(f"shot {i} must be an object, not a {type(raw).__name__}.")
        shot = {
            "n": i,
            "id": raw.get("id") or f"shot-{i:02d}",
            "beat": raw.get("beat") or "",
            "status": "planned",
            "panels": _normalise_panels(raw.get("panels") or [], defaults, raw),
            "motion": _normalise_motion(raw.get("motion") or {}, defaults),
            **_normalise_opens(raw, i),
        }
        # Recorded by `scenes render` / `scenes assemble`, never authored.
        for k in SHOT_RECORDED:
            shot[k] = raw.get(k)
        shot["status"] = shot_status(shot)
        shots.append(shot)

    plan_doc = {
        "slug": slug,
        "version": VERSION,
        "status": "planned",
        "characters": sorted(plan.get("characters") or []),
        "title": plan.get("title") or "",
        "logline": plan.get("logline") or "",
        # Prepended byte-identical to every panel prompt. Panels also inherit
        # each other so they converge on one look, but that is an image
        # argument and this is a wording one — location, wardrobe, light, grade
        # stated once and repeated exactly, the trick the reference angle spec
        # uses with its shared prose fragments. Cheap, and it survives a panel
        # being re-rendered on its own.
        "setting": plan.get("setting") or "",
        "defaults": defaults,
        "shots": shots,
    }
    plan_doc["status"] = scene_status(plan_doc)
    return plan_doc


def _panel_defaults(defaults: dict) -> dict:
    """The scene defaults as a PANEL sees them.

    `model` and `extra` at scene level are the video model and its technical
    block — `mode`, `generate_audio`, things an image model has never heard of.
    A panel inherits `panel_model` and `panel_extra` instead, under the names it
    uses, so one `_inherit` serves both halves without a panel silently asking
    for a still from a video engine.
    """
    return {
        "model": defaults.get("panel_model"),
        "extra": defaults.get("panel_extra") or {},
        "aspect_ratio": defaults.get("aspect_ratio"),
    }


def _normalise_panels(raw_panels: list, defaults: dict, shot: dict) -> list[dict]:
    panel_defaults = _panel_defaults(defaults)
    panels = []
    for j, raw in enumerate(raw_panels, 1):
        if not isinstance(raw, dict):
            raise PlanError(
                f"shot {shot.get('id') or '?'} panel {j} must be an object, "
                f"not a {type(raw).__name__}.")
        panel = {"n": j, "role": raw.get("role"), "prompt": raw.get("prompt") or ""}
        panel.update(_inherit(panel_defaults, raw, "model", "aspect_ratio", "extra"))
        # A panel renders like any other still: the model needs to be told who
        # this is, and that comes from the character's described index.
        panel["references"] = raw.get("references") or {}
        for k in PANEL_RECORDED:
            panel[k] = raw.get(k)
        panel["stale"] = bool(raw.get("stale"))
        panels.append(panel)
    return panels


def _normalise_motion(raw: dict, defaults: dict) -> dict:
    motion = {
        "prompt": raw.get("prompt") or "",
        "prompt_json": raw.get("prompt_json"),
        "references": raw.get("references") or {},
    }
    motion.update(_inherit(defaults, raw, "model", "duration", "aspect_ratio", "extra"))
    # The scene's own frames, not the character's curated set. Sending a
    # character's reference library mid-scene pulls the render toward the context
    # those images were shot in and fights the continuity the chain exists to
    # hold, so it stays empty unless the plan asks for it.
    motion["references"].setdefault("max_scene_frames", None)
    motion["references"].setdefault("characters", [])
    motion["references"].setdefault("keys", [])
    return motion


def _normalise_opens(raw: dict, n: int) -> dict:
    """Where a shot opens: the intent, plus the frame once it has been taken.

    `continues` is authored — does this shot pick up the movement of the one
    before it? Shot 1 has nothing before it; every later shot continues by
    default, which is the point of building a scene as a sequence rather than a
    pile of clips.

    `opens_on` is recorded by `scenes handoff`, never authored, and it names a
    **node id**. It named an S3 key until the entity model, so renaming the
    frame in the input pool silently detached it from the shot opening on it.
    """
    opens_on = raw.get("opens_on") or {}
    return {
        "continues": bool(raw["continues"]) if "continues" in raw else n > 1,
        "opens_on": {"node": opens_on.get("node"),
                     "from_run": opens_on.get("from_run")},
    }


def scene_frames(record: dict, max_n: int | None = None) -> list[str]:
    """The scene's OWN images as NODE IDS, in order — a shot's references.

    Derived, not stored. It used to live in a separate `chains/<slug>.json`,
    written alongside the scene and kept in sync by hand — which is the shape of
    every bug this repo has had to write a migrator for. A planned scene already
    records both halves: shot 1's opening panel is the seed, and every later
    shot's `opens_on.node` is the handoff frame produced by the shot before it.

    The seed anchors the look the whole scene inherits and the newest frames
    carry the current state, so when a cap forces a choice both ends are kept and
    the middle gives way.
    """
    shots = record.get("shots") or []
    nodes: list[str] = []
    if shots:
        roles = resolve_roles(shots[0])
        first = roles["start_panel"]
        if first is not None and roles["panels"][first].get("node"):
            nodes.append(roles["panels"][first]["node"])
    seeded = bool(nodes)
    for shot in shots:
        node = (shot.get("opens_on") or {}).get("node")
        if node and node not in nodes:
            nodes.append(node)

    if max_n is None or len(nodes) <= max_n:
        return nodes
    if not seeded:
        return nodes[-max_n:]
    # The seed always survives, and the newest frames fill what is left. Guard
    # the max_n == 1 case explicitly: `nodes[-0:]` is the WHOLE list, not the
    # empty one, so writing this as a single slice silently returns every frame
    # and the cap does nothing.
    return [nodes[0]] + (nodes[-(max_n - 1):] if max_n > 1 else [])


# --------------------------------------------------------------------------
# validating
# --------------------------------------------------------------------------

def validate(plan_doc: dict) -> None:
    """Refuse a plan that cannot mean anything. Registry-free by design.

    Whether a model takes an end frame, how many images it accepts and which
    formats it rejects are checked where the submit lifecycle already checks
    them; re-implementing those here is how two versions of a cap drift apart.
    """
    shots = plan_doc.get("shots")
    if not shots:
        raise PlanError("a scene needs at least one shot.")

    ids = [s["id"] for s in shots]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise PlanError(
            f"duplicate shot id(s): {', '.join(dupes)}\n"
            f"       Ids are how a re-ingest matches a revised plan against work "
            f"already paid for, so they have to be unique.")

    for shot in shots:
        where = f"shot {shot['id']}"
        panels = shot.get("panels") or []
        if not panels and not (shot.get("motion") or {}).get("prompt"):
            raise PlanError(f"{where} has neither a panel nor a motion prompt.")

        for panel in panels:
            if panel.get("role") and panel["role"] not in ROLES:
                raise PlanError(
                    f"{where} panel {panel['n']} has role {panel['role']!r}; "
                    f"expected one of {list(ROLES)}.")
            if not panel.get("prompt") and not panel.get("node"):
                raise PlanError(
                    f"{where} panel {panel['n']} has no prompt, so there is "
                    f"nothing to render it from.")

        roles = panel_roles(shot)
        for role in ("start", "end"):
            n = roles.count(role)
            if n > 1:
                named = [p["n"] for p, r in zip(panels, roles) if r == role]
                raise PlanError(
                    f"{where} has {n} panels acting as the {role} frame "
                    f"(panels {named}); a shot has at most one.")


# --------------------------------------------------------------------------
# roles — what each panel is FOR
# --------------------------------------------------------------------------

def is_supplied(panel: dict) -> bool:
    """A panel given as an image rather than as something to render.

    A plan can pin an image that already exists into the board — the frame a
    scene is to open on, or a pose pulled out of an earlier clip that is exactly
    right and would only be degraded by asking a model to reproduce it. Such a
    panel carries a `node` and no `prompt`, and the two commands that render
    panels must leave it alone: there is nothing to render, and nothing for it
    to be out of date with respect to.

    `node`, where this read `key`. A supplied panel is very often a frame lifted
    out of an earlier clip, which is exactly the file most likely to be renamed
    afterwards — and a key would then have stopped naming it.
    """
    return bool(panel.get("node")) and not (panel.get("prompt") or "").strip()


def panel_roles(shot: dict) -> list[str]:
    """One role per panel, positional unless the panel says otherwise.

    One panel is a start frame. Two are a start and an end. Three or more put the
    extras between them as references, because the middle of a movement is what
    a reference image is good at pinning.

    **Positions are counted over binding panels only.** A `sample` is not one of
    the shot's frames — it is a picture of the shot for a person to look at — so
    it must not consume the first or last position and turn the panel beside it
    into a reference. A shot boarded as `[sample, start]` has a start frame, not
    a start frame that got demoted by a picture.
    """
    panels = shot.get("panels") or []
    binding = [i for i, panel in enumerate(panels) if panel.get("role") != "sample"]
    last = binding[-1] if binding else None

    out = []
    for i, panel in enumerate(panels):
        if panel.get("role"):
            out.append(panel["role"])
        elif i == binding[0]:
            out.append("start")
        elif i == last:
            out.append("end")
        else:
            out.append("reference")
    return out


def resolve_roles(shot: dict) -> dict:
    """What this shot actually sends, once continuity has spoken.

    Returns panel *positions* rather than keys, so an unboarded panel is still
    reportable — the caller knows which panel is missing rather than just that
    something is None.

        handoff           node id of the previous shot's last frame, when this
                          shot continues it
        start_panel       index into `panels`, or None when the handoff took it
        end_panel         index, or None
        reference_panels  indices in panel order, demoted start first
        sample_panels     indices of panels that bind to nothing
        demoted           True when a start panel became a reference
    """
    panels = shot.get("panels") or []
    roles = panel_roles(shot)
    handoff = ((shot.get("opens_on") or {}).get("node")
               if shot.get("continues") else None)

    start = next((i for i, r in enumerate(roles) if r == "start"), None)
    end = next((i for i, r in enumerate(roles) if r == "end"), None)
    refs = [i for i, r in enumerate(roles) if r == "reference"]

    # The handoff is the literal last frame of the previous shot, so it is the
    # only image that makes the join invisible. The panel it displaces is not
    # discarded — it rides along steering where the shot goes.
    demoted = handoff is not None and start is not None
    if demoted:
        refs = sorted([start, *refs])
        start = None

    return {
        "handoff": handoff,
        "start_panel": start,
        "end_panel": end,
        "reference_panels": refs,
        # Reported so a board can draw them, never so a submit can bind them.
        "sample_panels": [i for i, r in enumerate(roles) if r == "sample"],
        "demoted": demoted,
        "roles": roles,
        "panels": panels,
    }


# --------------------------------------------------------------------------
# status — derived on every write, never read back as authority
# --------------------------------------------------------------------------

def shot_status(shot: dict) -> str:
    if shot.get("shot_node"):
        return "cut"
    if shot.get("run"):
        return "rendered"
    panels = shot.get("panels") or []
    binding = [p for p, r in zip(panels, panel_roles(shot)) if r != "reference"]
    if binding and all(p.get("node") for p in binding):
        return "boarded"
    return "planned"


def scene_status(record: dict) -> str:
    """Derived from the record and its shots, and PATCHed on every write.

    Recomputed rather than trusted off the row, which is the discipline the
    character index follows and for the same reason: a status stored and never
    recomputed is a claim nobody checks.
    """
    if (record.get("output") or {}).get("node"):
        return "assembled"
    states = [shot_status(s) for s in record.get("shots") or []]
    if not states:
        return "planned"
    if any(s in ("rendered", "cut") for s in states):
        return "shooting"
    if all(s == "boarded" for s in states):
        return "boarded"
    if any(s == "boarded" for s in states):
        return "boarding"
    return "planned"


def is_assembled(record: dict) -> bool:
    return bool((record.get("output") or {}).get("node"))


# --------------------------------------------------------------------------
# revising — a re-ingest must not orphan work already paid for
# --------------------------------------------------------------------------

def merge(old_shots: list[dict], new_shots: list[dict]) -> list[dict]:
    """Carry recorded work from an existing scene's shots onto a revised plan.

    Revising a scene means re-ingesting the whole plan, which would otherwise
    throw away every run and panel it already has. Shots are matched by their
    stable `id`, panels by number within a shot.

    **`PUT /api/scenes/<id>/shots` merges by shot id too, and this is still
    needed.** The API's merge is one level deep, so a revised shot's `panels`
    list replaces the stored one wholesale — a re-ingest sending only the
    author's panels would drop every `node` and `boarded` on them and orphan a
    board somebody paid for. The server's merge protects the shot; this protects
    what is inside it, and the two are not the same write.

    A panel whose prompt text changed keeps its image and is marked **stale**:
    the picture in the library no longer illustrates the words beside it. That
    is a warning rather than a block — the point of a board this cheap is that
    living with an out-of-date panel can be the right call.

    Scene-level carry-across went with the manifest. `created`, `stitch`,
    `output` and `assembled` are the record's and a re-ingest never sends them,
    so there is nothing left to preserve by hand.
    """
    by_id = {s["id"]: s for s in old_shots or []}
    for shot in new_shots or []:
        prev = by_id.get(shot["id"])
        if not prev:
            continue
        for k in SHOT_RECORDED:
            if shot.get(k) is None:
                shot[k] = prev.get(k)
        was_opens = prev.get("opens_on") or {}
        for k in ("node", "from_run"):
            if (shot.get("opens_on") or {}).get(k) is None:
                shot.setdefault("opens_on", {})[k] = was_opens.get(k)

        prev_panels = {p["n"]: p for p in prev.get("panels") or []}
        for panel in shot.get("panels") or []:
            was = prev_panels.get(panel["n"])
            if not was:
                continue
            for k in ("run", "source_node", "node", "boarded"):
                if panel.get(k) is None:
                    panel[k] = was.get(k)
            # A supplied panel has no prompt to have drifted from.
            if panel.get("node") and not is_supplied(panel):
                panel["stale"] = bool(was.get("stale")) or (
                    _text(panel.get("prompt")) != _text(was.get("prompt")))
            elif is_supplied(panel):
                panel["stale"] = False
        shot["status"] = shot_status(shot)
    return list(new_shots or [])


def _text(s: str | None) -> str:
    """Prompt text compared for meaning, not for whitespace."""
    return " ".join((s or "").split())


def panel_prompt(record: dict, panel: dict) -> str:
    """A panel's prompt with the scene's setting in front of it.

    The setting is repeated byte-identically across the board on purpose: Kling
    and the image models alike have no seed, so identical wording is the only
    reproducibility lever there is, and rewording between panels is how a board
    ends up self-consistent panel by panel and inconsistent overall.
    """
    setting = (record.get("setting") or "").strip()
    body = (panel.get("prompt") or "").strip()
    return f"{setting}\n\n{body}".strip() if setting else body


def board_order(record: dict) -> list[tuple[dict, dict]]:
    """Every (shot, panel) pair in board order — shot by shot, panel by panel.

    Panels are rendered in this order and each one sees the ones before it, so
    the order is not merely presentational: it is what each panel inherits.
    """
    return [(shot, panel)
            for shot in record.get("shots") or []
            for panel in shot.get("panels") or []]


# --------------------------------------------------------------------------
# reading the board
# --------------------------------------------------------------------------

def sheet_captions(record: dict) -> list[tuple[str, str]]:
    """(node id, caption) for every panel that exists, in board order.

    A contact sheet is the only way a board can be *read* — by a person scanning
    it, and by an agent, which otherwise has no way to check its own output. The
    caption carries the role because a panel's position in the sheet does not
    say whether it is a start frame, an end frame or a reference.
    """
    out = []
    for shot in record.get("shots") or []:
        roles = panel_roles(shot)
        for panel, role in zip(shot.get("panels") or [], roles):
            if not panel.get("node"):
                continue
            stale = " STALE" if panel.get("stale") else ""
            out.append((panel["node"], f"{shot['id']} p{panel['n']} [{role}]{stale}"))
    return out
