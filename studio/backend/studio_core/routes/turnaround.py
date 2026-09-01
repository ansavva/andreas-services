"""Draft a character's reference angles — the standard set, as unapproved runs.

**This is what made a turnaround reachable from anything but a terminal.** The
whole of it lived in `engine/turnaround.py` in the pipeline package: the spec,
the bible filling, the slot arithmetic and the drafting. So a reference render
could only be started by somebody with a checkout, and the SPA — which already
served the character, the pools, the runs and the approval — could not offer the
one operation those things exist for.

Nothing here approves anything, and nothing here spends. Every run it writes is
a `draft`: `NEVER_BILLED` names that state, the approval is a separate row bound
to a digest of the plan and its sends, and the API refuses to move a run out of
the unsubmitted states without one that still matches. Hard rule #2 is untouched
— this makes the payload, a person still says yes to it.

## Identity images are given, never guessed

The caller names the nodes that carry identity, in order. Resolving them here
would mean porting the seed-pool walk, the reference index and the
oversized-pool refusal — and it would take a decision away from the person
making it. WHICH photographs say who somebody is is the judgement a reference
library is built out of; a route that picked them by sort order would be making
it silently, which is exactly what `_too_many` exists to prevent on the other
side.

## Why the engine defaults are not in the spec

`model`, `aspect_ratio`, `output_format`, `quality` and `moderation` are engine
configuration rather than prose. A wrong one is a payload the provider rejects,
not a worse sentence, and preflight already covers it — so they stay here in
code while every word a person might want to change is a row.
"""

import logging

from flask import Blueprint, g, jsonify

from studio_core.errors import NotFoundError, ValidationError
from studio_core.routes import runs as run_routes
from studio_core.routes import support
from studio_core.services import catalog, reference, registry

logger = logging.getLogger(__name__)

bp = Blueprint("turnaround", __name__, url_prefix="/api")

#: The engine a reference angle renders on, and the knobs that go with it.
#: Chosen so any registered image model accepts the portable half: 2:3 is the
#: only portrait ratio all four take, and png is valid on all four despite the
#: enums differing — which keeps the output Kling-legal, the whole reason these
#: images exist.
DEFAULT_MODEL = "gpt-image-2"
PORTABLE_PARAMS = {"aspect_ratio": "2:3", "output_format": "png"}

#: Applied only when that model is the resolved one, so an override never
#: carries another model's vocabulary into a payload.
PER_MODEL_PARAMS = {
    "gpt-image-2": {"quality": "high", "moderation": "auto"},
    "gpt-image-1.5": {"quality": "high", "input_fidelity": "high"},
}


@bp.post("/characters/<character_id>/turnaround")
def draft_turnaround(character_id: str):
    """Write one draft per angle. Approves nothing, submits nothing, bills nothing."""
    body = support.body()
    held = support.memberships()
    record = support.entity_at(catalog.ENTITY_CHARACTER, g.library, character_id, held)

    # **Read first, because both of the guards below are about DRAFTING.**
    # A preview writes nothing, and the SPA now assembles one on every change so
    # a person can read what an angle would say while they are still choosing —
    # which is the use `_draft_one` was built for and says so. Requiring the
    # things a draft requires made that impossible: you could not see the words
    # until after every decision they were meant to inform.
    preview = bool(body.get("preview"))

    project = body.get("project")
    if not preview and (not isinstance(project, str) or not project):
        raise ValidationError("project is required — a run belongs to one, and "
                              "guessing puts runs somewhere nobody looks again")

    # **The anchor: an earlier render every angle in this pass is chained off.**
    #
    # A turnaround is not N independent shoots. Every hand-authored production
    # set was made as one anchor and then the rest chained off it, each binding
    # the anchor's output FIRST and each told to take the wardrobe and the
    # background from it — which is the only thing that held those constant
    # across a set. Shooting them independently is what produced fourteen
    # different shirts.
    #
    # A node id rather than a run id: the run is how the image was made and the
    # image is what gets bound, and a run may hold several outputs, so naming
    # the run would leave the choice of which one to send unmade.
    anchor = body.get("anchor")
    if anchor is not None and not (isinstance(anchor, str)
                                   and anchor.startswith("node-")):
        raise ValidationError("anchor must be a node id")

    identity = body.get("identity") or []
    per_angle = body.get("identity_by_angle") or {}
    if not isinstance(per_angle, dict):
        raise ValidationError("identity_by_angle must be an object keyed by angle id")
    if not isinstance(identity, list):
        raise ValidationError("identity must be a list of node ids")
    for nodes in [identity, *per_angle.values()]:
        if not isinstance(nodes, list):
            raise ValidationError("every identity selection must be a list of node ids")
        if not all(isinstance(n, str) and n.startswith("node-") for n in nodes):
            raise ValidationError("every identity entry must be a node id")

    spec = catalog.reference_spec(g.library)
    angles = _selected(spec["angles"], body.get("group"), body.get("angles"))

    # **Every angle must end up with photographs, and this is where that is
    # checked** — before any of them is drafted, so a shoot cannot half-happen
    # because the twelfth angle was the one nobody picked for.
    #
    # `identity_by_angle` beats `identity`, which is the fallback. Two shapes
    # because two callers want different things: the app picks per angle (a
    # profile angle wants the profile photographs, and a front angle does not),
    # while the CLI resolves ONE set from `--seed-pick` and means it for all of
    # them. A single shape would have made one of them lie.
    #
    # A PREVIEW is exempt. With no photographs the assembled prompt simply cites
    # no identity slots, which is a true answer to "what would this say so far"
    # — and refusing it is what forced a person to finish picking for fourteen
    # angles before they could read the words for one.
    unpicked = [a["id"] for a in angles
                if not (per_angle.get(a["id"]) or identity or anchor)]
    if unpicked and not preview:
        raise ValidationError(
            "no identity images for: " + ", ".join(unpicked) + ". Which "
            "photographs say who somebody is is not something this route may "
            "decide — pick for each angle, or send `identity` as a fallback.")
    if not angles:
        raise NotFoundError(
            "no angles matched. This library's reference spec holds "
            f"{len(spec['angles'])} angle(s); push one with `studio spec push` "
            "if it holds none.")

    model = body.get("model") or DEFAULT_MODEL
    entry = registry.find(model)
    if entry is None:
        raise ValidationError(f"unknown model {model!r} — see GET /api/models")
    if entry.get("kind") != "image":
        raise ValidationError(
            f"a reference angle is a still, but {entry['key']} is a "
            f"{entry.get('kind')} model")

    drafted, failed = [], []
    for angle in angles:
        try:
            picked = per_angle.get(angle["id"]) or identity
            # First, and de-duplicated: `[Image1]` is what the `anchor` block
            # names, so the position is part of the contract rather than a
            # coincidence of ordering.
            if anchor:
                picked = [anchor] + [n for n in picked if n != anchor]
            drafted.append(_draft_one(angle, spec["blocks"], record, entry,
                                      # A preview never reaches the draft the
                                      # project would go on.
                                      project if isinstance(project, str) else "",
                                      picked, body, held,
                                      preview=preview, anchored=bool(anchor)))
        except (ValidationError, NotFoundError) as refusal:
            # ONE BAD ANGLE DOES NOT CANCEL THE REST. A failure here is almost
            # always a property of that angle alone — a template citing a block
            # somebody deleted, most often — and says nothing about the others.
            # Aborting on the first cost a live turnaround six healthy angles
            # once, because the failing one happened to sort first.
            failed.append({"angle": angle["id"], "error": str(refusal)})

    if preview:
        # Writes nothing, so 200 rather than 201 and `preview` rather than
        # `drafted` — a caller must not be able to mistake one for the other and
        # then look for run ids that were never minted.
        return jsonify({"preview": drafted, "failed": failed}), 200
    return jsonify({"drafted": drafted, "failed": failed}), 201


def _selected(angles: list, group, wanted) -> list:
    """The angles this request is about, in the spec's own order."""
    if wanted is not None:
        if not isinstance(wanted, list):
            raise ValidationError("angles must be a list of angle ids")
        chosen = set(wanted)
        picked = [a for a in angles if a["id"] in chosen]
        missing = chosen - {a["id"] for a in picked}
        if missing:
            raise NotFoundError(
                f"no such angle(s): {', '.join(sorted(missing))}. "
                f"This library has: {', '.join(a['id'] for a in angles)}")
        return picked
    if group:
        if group not in ("face", "body"):
            raise ValidationError("group must be 'face' or 'body'")
        return [a for a in angles if a.get("group") == group]
    return list(angles)


def _draft_one(angle: dict, blocks: dict, character: dict, entry: dict,
               project: str, identity: list, body: dict, held,
               preview: bool = False, anchored: bool = False) -> dict:
    """Assemble one angle, and write it as a draft unless this is a preview.

    The preview exists because the CLI's `--dry-run` and the SPA's live editor
    ask the same question — *what would this angle say?* — and answering it
    twice would be two assemblies to keep in step. It stops before the write, so
    it is safe to call on every keystroke of an editor, which is the same
    property `POST /api/prompt` is built around.
    """
    # The identity images, in the order they were picked — which is the order
    # the model is handed them and therefore the order `[ImageN]` counts in.
    # Positions are read back off THIS list rather than assumed, because a
    # template citing a hard-coded number aims its instruction at whatever
    # happens to sit there.
    ordered = list(identity)
    identity_positions = [i + 1 for i in range(len(ordered))]

    prompt = reference.assemble(angle, blocks, character.get("profile") or {},
                                identity_positions=identity_positions,
                                anchored=anchored)

    params = {**PORTABLE_PARAMS,
              **PER_MODEL_PARAMS.get(entry["key"], {}),
              **(body.get("extra") or {})}
    field = (entry.get("images") or {}).get("refs")
    if not field:
        raise ValidationError(f"{entry['key']} takes no reference images")

    draft = {
        "project": project,
        "kind": "image",
        "engine": entry.get("skill"),
        "model": entry.get("model") or entry["key"],
        "name": f"ref-{angle['id'].replace('_', '-')}",
        "characters": [character["id"]],
        "plan": {"version": 1, "origin": "authored",
                 "prompt": prompt, "params": params},
        "sends": [{"field": field, "role": "reference", "node": node}
                  for node in ordered],
    }
    if preview:
        return {"angle": angle["id"], "plan": draft["plan"],
                "model": draft["model"], "sends": draft["sends"]}
    # The PLAN comes back on the drafted entry too, so a caller that has to show
    # somebody the payload does not have to assemble it a second time or re-read
    # the run. Assembling twice is two chances to differ; re-reading is a request
    # per angle to see what this one already holds.
    return run_routes.create_draft(draft, held) | {
        "angle": angle["id"], "plan": draft["plan"], "model": draft["model"]}
