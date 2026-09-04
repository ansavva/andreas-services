"""The scene plan: what an authored storyboard means, and what it cannot mean.

**This lived in the pipeline and the API stored what it was handed.** `POST
/api/scenes` and `PATCH /api/scenes/<id>/shots` wrote `SHOT#` rows without ever
asking whether the plan was coherent — whether a shot had anything to render
from, whether two panels both claimed to be the start frame, whether the ids a
re-ingest matches on were even unique. `catalog.put_shots` merged by id and that
was the whole of the server's opinion.

The consequence was not that bad plans got in. It was that **the SPA rendered a
status the CLI had computed.** `shot_status` and `scene_status` are derivations —
a shot is `boarded` when every binding panel has an image, a scene is `shooting`
when any shot has a run — and they were derived on one client and stored on the
row. Anything that wrote a shot without recomputing them left a scene claiming to
be `planned` with three rendered shots under it, and nothing anywhere would
notice. A status stored and never recomputed is a claim nobody checks.

So the derivations happen here, on read, and the validation happens on write.

## What stayed in the pipeline

`load_plan` reads a file off disk and `merge` is `catalog.put_shots`' job
already. `board_order` and `sheet_captions` order panels for rendering and for a
contact sheet — both are about invoking a model or drawing a grid, which is work
this service does not do and will not until the render worker exists.

## What is deliberately NOT checked here

Whether a model takes an end frame, how many images it accepts, which formats it
rejects. Those are registry questions asked where the submit lifecycle already
asks them, and a copy here is how two versions of a cap drift apart. The plan is
checked for being *meaningless*, not for being unaffordable.

## Roles, and why a handoff outranks a panel

Panels are positional: the first is the start frame, the last the end frame,
anything between them a reference. A panel may say `role` outright and win.

Then continuity speaks. A shot that continues the one before it opens on that
shot's **literal last frame**, and only that frame makes the cut seamless — a
storyboard panel, however carefully composed, differs from it in a hundred small
ways that read as a jump. So when a shot has a handoff frame the handoff becomes
the start frame and the start *panel is demoted to a reference*, still steering
where the shot goes without breaking the join. Shot 1 has nothing before it, so
its first panel really is the start. `"continues": false` forces the panel back.
"""

from __future__ import annotations


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
# normalising — filling in what a plan left implicit
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


def normalise(plan: dict, name: str) -> dict:
    """A plan as authored -> the body `POST /api/scenes` takes, nothing implicit.

    Numbering, ids, inherited defaults and derived status are all filled in here
    so that everything downstream reads one shape. Recorded fields (`run`,
    `node`, …) are initialised to None and are the tools' to write, never the
    author's.

    **Takes no project and returns no manifest.** A scene's project, id,
    timings, stitch and output are on the record and the API owns every one of
    them; returning copies here would be a second truth for a rename or a re-cut
    to leave behind.
    """
    defaults = dict(plan.get("defaults") or {})

    shots = []
    for i, raw in enumerate(plan.get("shots") or [], 1):
        if not isinstance(raw, dict):
            raise PlanError(f"shot {i} must be an object, not a {type(raw).__name__}.")
        # **SPARSE: only what the author named, plus what is derived.**
        #
        # `catalog.put_shots` merges with `entry.get(field, previous.get(field))`,
        # so **naming a field wins** — a default such as `panels: []` or
        # `run: None` would overwrite recorded work.
        # A revision that renamed a beat would have arrived carrying `panels: []`
        # and `run: None` and wiped the boarded panel and the rendered run
        # underneath it.
        #
        # So a key appears here only if the author wrote one. `id`, `n` and
        # `status` are the exceptions, because all three are derived rather than
        # authored and are wanted on every write.
        shot = {"n": i, "id": raw.get("id") or f"shot-{i:02d}", "status": "planned"}
        for field in ("beat", "prompt"):
            if field in raw:
                shot[field] = raw[field] or ""
        if "panels" in raw:
            shot["panels"] = _normalise_panels(raw.get("panels") or [], defaults, raw)
        if "motion" in raw:
            shot["motion"] = _normalise_motion(raw.get("motion") or {}, defaults)
        # `continues` is DERIVED — shot 1 opens cold, every later shot picks up
        # the movement of the one before it unless the author says otherwise — so
        # it is written every time. `opens_on` is RECORDED by `scenes handoff`
        # and is only carried when the author named one, for the reason the
        # recorded fields below are: it would otherwise wipe a handoff frame.
        opens = _normalise_opens(raw, i)
        shot["continues"] = opens["continues"]
        if "opens_on" in raw:
            shot["opens_on"] = opens["opens_on"]
        # **Recorded by the render commands, never authored — and only carried
        # when the author actually named one.**
        #
        # `catalog.put_shots` merges with `entry.get(field, previous.get(field))`,
        # so **naming a field wins** — a `run: None` written unconditionally
        # would beat the run id already on the row. A plan
        # revision would have silently unlinked every rendered shot it touched.
        for k in SHOT_RECORDED:
            if k in raw:
                shot[k] = raw[k]
        shot["status"] = shot_status(shot)
        shots.append(shot)

    plan_doc = {
        "name": name,
        "version": VERSION,
        "status": "planned",
        "characters": sorted(plan.get("characters") or []),
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

    Derived, not stored: a planned scene already records both halves — shot 1's
    opening panel is the seed, and every later
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
    """Refuse a plan that cannot be STORED coherently. Not one that cannot be shot.

    **The line moved when this became a server-side check, and the distinction is
    the whole of it.** In the pipeline this ran over a finished plan read from a
    JSON file, so "shot 3 has nothing to render from" was a useful early error
    about a typo. As a store invariant it is wrong: a person sketching beats
    before writing any prompts is authoring normally, and the SPA's plan editor
    would have been refused on its first save. `shot_status` already reports such
    a shot as `planned`, which is the honest answer.

    So what is enforced here is what makes a plan incoherent *as data*:

      * duplicate shot ids — the merge matches on them, and two shots sharing one
        collapse onto a single row on the next revision;
      * a role outside the enum;
      * two panels both claiming to be the start or end frame, which is
        positionally impossible rather than merely unfinished.

    Render-readiness stays where it can still be useful — the ingest path, which
    knows it was handed something a person called finished.

    Registry-free by design either way. Whether a model takes an end frame, how
    many images it accepts and which formats it rejects are checked where the
    submit lifecycle already checks them; a copy here is how two versions of a
    cap drift apart.
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

        for panel in panels:
            if panel.get("role") and panel["role"] not in ROLES:
                raise PlanError(
                    f"{where} panel {panel['n']} has role {panel['role']!r}; "
                    f"expected one of {list(ROLES)}.")

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
    """Derived from the record and its shots, on every read and every write.

    Recomputed rather than trusted off the row, which is the discipline the
    character index follows and for the same reason: a status stored and never
    recomputed is a claim nobody checks.
    """
    if _output_node(record):
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
    return bool(_output_node(record))


def _output_node(record: dict) -> str | None:
    """The cut's node id, whichever of the two shapes the row holds.

    **A bare string is the shape prod was written in.** `output` became
    `{node, …}` and `support.with_output` normalises it on the way out — but
    these derivations run against the raw record too (on write, where nothing has
    normalised anything yet), and `("a-node-id").get("node")` is an
    `AttributeError` that takes the whole request with it. Reading either shape
    here is cheaper than making every caller remember which one it holds.
    """
    output = record.get("output")
    if isinstance(output, str):
        return output or None
    return (output or {}).get("node")


#: The same normaliser, under a name a module outside this one may say. Both
#: shapes are live — a bare id is what prod was written in — and `services/render`
#: has to read the displaced cut off a raw record before it writes the new one.
output_node = _output_node


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


def unrenderable(plan_doc: dict) -> list[str]:
    """What in this plan could not be shot as it stands. **Advisory, never fatal.**

    Separate from `validate` because they are the right thing to tell somebody
    who just handed over a finished plan, not a reason to refuse it — a shot with
    no words in it anywhere is nearly always a typo, not a deliberate blank. Returned as a list so the caller decides: the ingest path prints them
    and refuses, and a save from a plan editor ignores them.

    **Three ways a shot can say what to render, and the pipeline's validator knew
    two.** It checked `panels` and `motion.prompt`, because that is what
    `normalise` produces from an authored plan. The row has a third — a bare
    `prompt`, in `catalog.SHOT_FIELDS` and a required field on the SPA's `Shot`
    type. Found by moving the check to where the row is written.
    """
    problems = []
    for shot in plan_doc.get("shots") or []:
        where = f"shot {shot['id']}"
        panels = shot.get("panels") or []
        if not panels and not (shot.get("motion") or {}).get("prompt") \
                and not (shot.get("prompt") or "").strip():
            problems.append(f"{where} has nothing to render from — no panel, "
                            f"no motion prompt, and no prompt.")
        for panel in panels:
            if not panel.get("prompt") and not panel.get("node"):
                problems.append(f"{where} panel {panel['n']} has no prompt and "
                                f"no image, so there is nothing to render it from.")
    return problems


TAKE_FIELDS = ("run", "runref", "node", "rendered")


def keep_take(previous: dict, merged: dict) -> list[dict]:
    """The runs a shot has been rendered by, newest-current-first behind it.

    A shot holds one `run`, so a re-render — a wording change, a beat that came
    out wrong, a wedged run resubmitted — would otherwise leave the take before
    it reachable only by an id you had written down.

    So the displaced take is pushed here rather than dropped. It is kept as the
    four fields that let it be drawn and opened and no more; the run is the
    record, and duplicating it would be a second copy to keep true.

    **Deduplicated on `run`, and that is what makes this safe to call on every
    write.** `put_shots` runs on every plan revision and `update_shot` on every
    field patch, so a shot gets written many times per render with the same run
    in place. Only a run that is actually being displaced is pushed, and a run
    already in the list is not pushed twice — otherwise a `--force` re-ingest
    would grow the history by one entry per ingest, for ever.
    """
    was, now = previous.get("run"), merged.get("run")
    # The base list comes off `merged`, not off `previous`. Both writers build
    # `merged` as `{**stored, **changes}`, so this is the stored history unless
    # a caller named `takes` explicitly — and a caller that did means it. That
    # is the only way to state a history the API never saw happen: takes are
    # normally a by-product of displacement, so a shot re-rendered before this
    # field existed has runs that are real and a history that is empty, and
    # nothing could put them back. Reading `previous` here made the field
    # write-only, which is a strange thing for a field to be.
    takes = [dict(take) for take in (merged.get("takes") or [])]
    if not was or was == now:
        return takes
    if any(take.get("run") == was for take in takes):
        return takes
    return [{field: previous.get(field) for field in TAKE_FIELDS}, *takes]


def merge_panels(previous: dict, revised: dict) -> list[dict]:
    """Carry a shot's recorded panel work onto its revised panels, matched by `n`.

    **`put_shots` merges one level deep, and this is the level below it.** A
    revision that names `panels` replaces the stored list wholesale, so every
    `node` and `boarded` on them would be dropped and a board somebody paid for
    orphaned. The shot-level merge protects the shot; this protects what is
    inside it, and the two are not the same write.

    This ran in the pipeline — `storyboard.merge`, whose own docstring explained
    that it existed *because* the API's merge was one level deep. That made the
    CLI the only client that could revise a plan safely: the SPA has no such
    pre-pass, so a plan editor saving a reworded beat would have wiped the images
    under it. It belongs where the merge it completes lives.

    A panel whose prompt text changed keeps its image and is marked **stale**:
    the picture in the library no longer illustrates the words beside it. That is
    a warning rather than a block — the point of a board this cheap is that
    living with an out-of-date panel can be the right call.
    """
    panels = revised.get("panels")
    if panels is None:
        return None
    was_by_n = {p.get("n"): p for p in previous.get("panels") or []}
    merged = []
    for panel in panels:
        panel = dict(panel)
        was = was_by_n.get(panel.get("n"))
        if was:
            for field in ("run", "source_node", "node", "boarded"):
                if panel.get(field) is None:
                    panel[field] = was.get(field)
            # **Derived only when the caller did not say**, which is the same
            # rule the shot-level merge follows. `scenes board --redo` marks a
            # panel stale deliberately to force a re-render, and a merge that
            # recomputed unconditionally answered `False` — the previous panel
            # was not stale and the prompt had not changed — so the flag was
            # dropped on the write that was supposed to set it.
            if "stale" in panel:
                pass
            elif is_supplied(panel):
                panel["stale"] = False
            elif panel.get("node"):
                panel["stale"] = bool(was.get("stale")) or (
                    _text(panel.get("prompt")) != _text(was.get("prompt")))
        merged.append(panel)
    return merged


def keep_cut(record: dict, node_id: str | None) -> list[dict]:
    """The cuts this scene or movie has been assembled into before the current one.

    **Re-cutting overwrote the only pointer to the previous take.** A scene holds
    one `output` — deliberately, because a scene *is* one take — but assembling
    is not a one-shot act: a shot gets re-rendered and the scene is cut again,
    and the stitched file that was there is then reachable by nobody.

    Same shape and same rules as `keep_take` above: only a node actually being
    displaced is pushed, and a node already in the list is not pushed twice, so
    the repeated writes that a single assemble makes cannot grow the history.

    **It lives here rather than in `routes/support.py`, where it was written.**
    The assemble that displaces a cut runs in the render worker now, which has no
    Flask request and must not import a route module to reach a pure function.
    `support.keep_cut` delegates, so there is one implementation and the route
    keeps its name.
    """
    was = _output_node(record)
    cuts = [dict(cut) for cut in (record.get("cuts") or [])]
    if not was or was == node_id:
        return cuts
    if any(cut.get("node") == was for cut in cuts):
        return cuts
    stored = record.get("output")
    stored = {} if isinstance(stored, str) else dict(stored or {})
    return [{**stored, "node": was}, *cuts]
