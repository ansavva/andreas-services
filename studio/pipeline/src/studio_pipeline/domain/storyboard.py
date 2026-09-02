"""The scene plan, as far as the CLI still needs to read one.

**Most of this module is `backend/studio_core/services/storyboard.py` now.**
Normalising an authored plan, validating it, merging a revision onto rendered
work and deriving every status are the API's — they were derivations run on one
client and stored, so anything that wrote a shot without repeating them left the
SPA drawing a stale answer. A status stored and never recomputed is a claim
nobody checks.

What is left is what only a local command has any use for:

  * `load_plan` reads a JSON file off disk, which the API cannot do;
  * `check_scene_slug` refuses a `<project>/<slug>` typed at a prompt before a
    request is spent finding out;
  * `scene_frames`, `resolve_roles`, `panel_roles`, `is_supplied`,
    `panel_prompt`, `board_order` and `sheet_captions` are read by
    `engine/board.py` while it decides what to submit and by `scenes sheet`
    while it draws a grid. Both are model invocation and image work, which this
    service does not do — so they follow `board.py` and the contact sheet
    whenever those move, and not before.

`scene_frames` and `resolve_roles` are also served by the API — the scene view
carries `frames`, and each shot carries `roles`. The copies here are what
`board.py` uses on material it has just built and not yet written, which is the
one case a served derivation cannot answer.

## Roles, and why a handoff outranks a panel

Panels are positional: the first is the start frame, the last the end frame, and
anything between them is a reference. A panel may say `role` outright and win.

Then continuity speaks. A shot that continues the one before it opens on that
shot's **literal last frame**, and only that frame makes the cut seamless — a
storyboard panel, however carefully composed, will differ from it in a hundred
small ways that read as a jump. So when a shot has a handoff frame, the handoff
becomes the start frame and the start *panel is demoted to a reference*, still
steering where the shot goes without breaking the join. Shot 1 has nothing
before it, so its first panel really is the start.

`"continues": false` on a shot forces the panel back — the right answer when a
shot deliberately opens on a new composition rather than continuing a movement.
"""

from __future__ import annotations

import json


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


def check_scene_name(name: str) -> str:
    """A scene's name: a label, and nothing more.

    **Two rules died here.** It refused anything shaped like a run id, because a
    scene folder was once `<timestamp>_<slug>` and a new scene named that way
    would have been indistinguishable from one of them; and it enforced the slug
    character class, because the name became a path segment. A scene is a row
    with a UUID, its folder is named by that id, and its name is a free-text
    label — so the only thing left worth refusing is an empty one.
    """
    folded = " ".join((name or "").split())
    if not folded:
        raise PlanError("a scene needs a name")
    return folded


# --------------------------------------------------------------------------
# normalising — fill in what the plan left implicit
# --------------------------------------------------------------------------

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

def is_assembled(record: dict) -> bool:
    return bool((record.get("output") or {}).get("node"))


# --------------------------------------------------------------------------
# revising — a re-ingest must not orphan work already paid for
# --------------------------------------------------------------------------

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
