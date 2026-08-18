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
`reference_shots.yaml` is a spec that ships in the package, because every
character's reference set is the same fourteen angles. A storyboard is the
opposite: it is prose about one particular scene, and prose about a scene names
what happens in it. That cannot live in this repository (see `studio/CLAUDE.md`,
hard rule 1), so a plan is authored outside it, ingested with
`studio scenes new --from-json`, and stored in S3 as `scene.json`.

This module is the document and nothing else — no S3, no models, no Click. It
loads a plan, fills in what the plan left implicit, refuses a plan that cannot
mean anything, and answers the one question the rest of the code needs:

    resolve_roles(shot)  ->  which panel is the start frame, which is the end,
                             and which merely ride along as references

ROLES, AND WHY THE CHAIN OUTRANKS A PANEL
-----------------------------------------
Panels are positional: the first is the start frame, the last the end frame, and
anything between them is a reference. A panel may say `role` outright and win.

Then the chain speaks. A chained scene hands each shot the **literal last frame**
of the shot before it, and that frame is what makes the cut seamless — a
storyboard panel, however carefully composed, will differ from it in a hundred
small ways that read as a jump. So when a shot has a handoff frame, the handoff
becomes the start frame and the start *panel is demoted to a reference*, still
steering where the shot goes without breaking the join. Shot 1 has no handoff, so
its first panel really is the start.

`use_handoff: false` on a shot forces the panel back — the right answer when a
shot deliberately opens on a new composition rather than continuing a movement.

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
from studio_pipeline.domain import runs as R

# The plan shape. Bumped when a field changes meaning, not when one is added —
# `scene.json` documents predating storyboards carry no version at all and are
# read as v1: a finished cut with no plan behind it.
VERSION = 2

ROLES = ("start", "end", "reference")

#: A shot's progress, derived from what it has rather than declared.
SHOT_STATUS = ("planned", "boarded", "rendered", "cut")
SCENE_STATUS = ("planned", "boarding", "boarded", "shooting", "assembled")

#: Panel fields the plan author writes. Everything else on a panel is recorded
#: by the tools and carried across a re-ingest.
PANEL_AUTHORED = ("role", "prompt", "model", "aspect_ratio", "extra", "references")
PANEL_RECORDED = ("run", "source_key", "key", "boarded", "stale")


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
    """A scene slug, which is also its directory name.

    Refuses anything shaped like a run id as well as the usual rules. Scene
    folders used to be `<timestamp>_<slug>`; those still exist and still resolve,
    so a *new* scene called `2026-08-16_07-40-22_something` would be
    indistinguishable from one of them.
    """
    try:
        P.check_slug(slug, "scene slug")
    except P.PathError as exc:
        raise PlanError(str(exc)) from exc
    if R.RUN_ID_RE.match(slug):
        raise PlanError(
            f"scene slug {slug!r} is shaped like a run id, which a scene folder "
            f"used to be.\n"
            f"       A scene created today is keyed by its slug alone — pick a "
            f"name, not a timestamp.")
    return slug


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


def normalise(plan: dict, project: str, slug: str) -> dict:
    """A plan as authored -> the full `scene.json` shape, with nothing implicit.

    Numbering, ids, inherited defaults and derived status are all filled in here
    so that everything downstream reads one shape. Recorded fields (`run`, `key`,
    …) are initialised to None and are the tools' to write, never the author's.
    """
    defaults = dict(plan.get("defaults") or {})
    defaults.setdefault("chain", slug)

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
            "chain": _normalise_chain(raw.get("chain") or {}, defaults, i),
        }
        # Recorded by `scenes render` / `scenes assemble`, never authored.
        for k in ("run", "runref", "key", "shot_key", "duration", "rendered"):
            shot[k] = raw.get(k)
        shot["status"] = shot_status(shot)
        shots.append(shot)

    manifest = {
        "scene": f"{project}/{slug}",
        "project": project,
        "slug": slug,
        "version": VERSION,
        "status": "planned",
        "characters": sorted(plan.get("characters") or []),
        "created": plan.get("created") or R._now(),
        "updated": R._now(),
        "title": plan.get("title") or "",
        "logline": plan.get("logline") or "",
        "defaults": defaults,
        "shots": shots,
        "stitch": plan.get("stitch"),
        "output": plan.get("output"),
        "assembled": plan.get("assembled"),
    }
    manifest["status"] = scene_status(manifest)
    return manifest


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
    motion["references"].setdefault("chain", defaults.get("chain"))
    motion["references"].setdefault("characters", [])
    motion["references"].setdefault("keys", [])
    return motion


def _normalise_chain(raw: dict, defaults: dict, n: int) -> dict:
    return {
        "slug": raw.get("slug") or defaults.get("chain"),
        # Shot 1 has nothing to hand off from. Every later shot continues by
        # default, which is the whole point of building a scene as a chain.
        "use_handoff": bool(raw["use_handoff"]) if "use_handoff" in raw else n > 1,
        "start_key": raw.get("start_key"),
        "from_run": raw.get("from_run"),
    }


# --------------------------------------------------------------------------
# validating
# --------------------------------------------------------------------------

def validate(manifest: dict) -> None:
    """Refuse a plan that cannot mean anything. Registry-free by design.

    Whether a model takes an end frame, how many images it accepts and which
    formats it rejects are checked where the submit lifecycle already checks
    them; re-implementing those here is how two versions of a cap drift apart.
    """
    shots = manifest.get("shots")
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
            if not panel.get("prompt") and not panel.get("key"):
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

def panel_roles(shot: dict) -> list[str]:
    """One role per panel, positional unless the panel says otherwise.

    One panel is a start frame. Two are a start and an end. Three or more put the
    extras between them as references, because the middle of a movement is what
    a reference image is good at pinning.
    """
    panels = shot.get("panels") or []
    last = len(panels) - 1
    out = []
    for i, panel in enumerate(panels):
        if panel.get("role"):
            out.append(panel["role"])
        elif i == 0:
            out.append("start")
        elif i == last:
            out.append("end")
        else:
            out.append("reference")
    return out


def resolve_roles(shot: dict) -> dict:
    """What this shot actually sends, after the chain has spoken.

    Returns panel *positions* rather than keys, so an unboarded panel is still
    reportable — the caller knows which panel is missing rather than just that
    something is None.

        handoff           the chain's frame, when this shot continues one
        start_panel       index into `panels`, or None when the handoff took it
        end_panel         index, or None
        reference_panels  indices in panel order, demoted start first
        demoted           True when a start panel became a reference
    """
    panels = shot.get("panels") or []
    roles = panel_roles(shot)
    chain = shot.get("chain") or {}
    handoff = chain.get("start_key") if chain.get("use_handoff") else None

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
        "demoted": demoted,
        "roles": roles,
        "panels": panels,
    }


# --------------------------------------------------------------------------
# status — derived on every write, never read back as authority
# --------------------------------------------------------------------------

def shot_status(shot: dict) -> str:
    if shot.get("shot_key"):
        return "cut"
    if shot.get("run"):
        return "rendered"
    panels = shot.get("panels") or []
    binding = [p for p, r in zip(panels, panel_roles(shot)) if r != "reference"]
    if binding and all(p.get("key") for p in binding):
        return "boarded"
    return "planned"


def scene_status(manifest: dict) -> str:
    if (manifest.get("output") or {}).get("key"):
        return "assembled"
    states = [shot_status(s) for s in manifest.get("shots") or []]
    if not states:
        return "planned"
    if any(s in ("rendered", "cut") for s in states):
        return "shooting"
    if all(s == "boarded" for s in states):
        return "boarded"
    if any(s == "boarded" for s in states):
        return "boarding"
    return "planned"


def is_assembled(manifest: dict) -> bool:
    return bool((manifest.get("output") or {}).get("key"))


# --------------------------------------------------------------------------
# revising — a re-ingest must not orphan work already paid for
# --------------------------------------------------------------------------

def merge(old: dict, new: dict) -> dict:
    """Carry recorded work from an existing scene onto a revised plan.

    Revising a scene means re-ingesting the whole document, which would otherwise
    throw away every run and panel it already has. Shots are matched by their
    stable `id`, panels by number within a shot.

    A panel whose prompt text changed keeps its image and is marked **stale**:
    the picture on disk no longer illustrates the words beside it. That is a
    warning rather than a block — the point of a board this cheap is that living
    with an out-of-date panel can be the right call.
    """
    by_id = {s["id"]: s for s in old.get("shots") or []}
    for shot in new.get("shots") or []:
        prev = by_id.get(shot["id"])
        if not prev:
            continue
        for k in ("run", "runref", "key", "shot_key", "duration", "rendered"):
            if shot.get(k) is None:
                shot[k] = prev.get(k)
        prev_chain = prev.get("chain") or {}
        for k in ("start_key", "from_run"):
            if (shot.get("chain") or {}).get(k) is None:
                shot["chain"][k] = prev_chain.get(k)

        prev_panels = {p["n"]: p for p in prev.get("panels") or []}
        for panel in shot.get("panels") or []:
            was = prev_panels.get(panel["n"])
            if not was:
                continue
            for k in ("run", "source_key", "key", "boarded"):
                if panel.get(k) is None:
                    panel[k] = was.get(k)
            if panel.get("key"):
                panel["stale"] = bool(was.get("stale")) or (
                    _text(panel.get("prompt")) != _text(was.get("prompt")))
        shot["status"] = shot_status(shot)

    for k in ("created", "stitch", "output", "assembled"):
        if new.get(k) is None:
            new[k] = old.get(k)
    new["status"] = scene_status(new)
    return new


def _text(s: str | None) -> str:
    """Prompt text compared for meaning, not for whitespace."""
    return " ".join((s or "").split())


# --------------------------------------------------------------------------
# reading the board
# --------------------------------------------------------------------------

def sheet_captions(manifest: dict) -> list[tuple[str, str]]:
    """(key, caption) for every panel that exists, in board order.

    A contact sheet is the only way a board can be *read* — by a person scanning
    it, and by an agent, which otherwise has no way to check its own output. The
    caption carries the role because a panel's position in the sheet does not
    say whether it is a start frame, an end frame or a reference.
    """
    out = []
    for shot in manifest.get("shots") or []:
        roles = panel_roles(shot)
        for panel, role in zip(shot.get("panels") or [], roles):
            if not panel.get("key"):
                continue
            stale = " STALE" if panel.get("stale") else ""
            out.append((panel["key"], f"{shot['id']} p{panel['n']} [{role}]{stale}"))
    return out
