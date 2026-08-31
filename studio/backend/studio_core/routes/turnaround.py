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

    project = body.get("project")
    if not isinstance(project, str) or not project:
        raise ValidationError("project is required — a run belongs to one, and "
                              "guessing puts runs somewhere nobody looks again")

    identity = body.get("identity") or []
    if not isinstance(identity, list) or not identity:
        raise ValidationError(
            "identity must be a non-empty list of node ids — which photographs "
            "carry identity is not something this route may decide")
    if not all(isinstance(node, str) and node.startswith("node-") for node in identity):
        raise ValidationError("every identity entry must be a node id")

    spec = catalog.reference_spec(g.library)
    angles = _selected(spec["angles"], body.get("group"), body.get("angles"))
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

    preview = bool(body.get("preview"))
    drafted, failed = [], []
    for angle in angles:
        try:
            drafted.append(_draft_one(angle, spec["blocks"], record, entry,
                                      project, identity, body, held,
                                      preview=preview))
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


def _plate_nodes(angle: dict, lib: str) -> list:
    """The guide images this angle binds, resolved to node ids, in citation order.

    An angle may bind none — the face angles do not, because a plate saying how
    to stand was measurably distorting the face it existed to record. A body
    angle binds one, and the spec stores it as a name path under `config/` so
    the prose names the object rather than a uuid nobody can read.
    """
    nodes = []
    for field in ("angle_image", "torso_image"):
        path = angle.get(field)
        if not path:
            continue
        # The same walk `GET /api/resolve` does, and for the same reason: the
        # spec stores an ADDRESS. Splitting on `/` is unambiguous by
        # construction — `keys.clean_name` refuses a slash in a name — so no
        # stored name can contain a separator.
        node_id = catalog.library(lib)["root_node"]
        try:
            for name in [seg for seg in path.split("/") if seg]:
                node_id = catalog.child_by_name(node_id, name)["node_id"]
        except NotFoundError:
            raise NotFoundError(
                f"angle {angle['id']!r} binds {path!r}, which has no node. "
                f"Guide images are pushed by `studio config sync`.")
        nodes.append(node_id)
    return nodes


def _draft_one(angle: dict, blocks: dict, character: dict, entry: dict,
               project: str, identity: list, body: dict, held,
               preview: bool = False) -> dict:
    """Assemble one angle, and write it as a draft unless this is a preview.

    The preview exists because the CLI's `--dry-run` and the SPA's live editor
    ask the same question — *what would this angle say?* — and answering it
    twice would be two assemblies to keep in step. It stops before the write, so
    it is safe to call on every keystroke of an editor, which is the same
    property `POST /api/prompt` is built around.
    """
    plates = _plate_nodes(angle, character["lib"])
    # The plates first and identity after, which is the order the model is
    # handed them and therefore the order `[ImageN]` counts in. Positions are
    # read back off THIS list rather than assumed, because a template citing a
    # hard-coded number aims its instruction at whatever happens to sit there.
    ordered = plates + [n for n in identity if n not in plates]
    angle_position = ordered.index(plates[0]) + 1 if plates else None
    torso_position = ordered.index(plates[1]) + 1 if len(plates) > 1 else None
    identity_positions = [i + 1 for i, node in enumerate(ordered) if node not in plates]

    prompt = reference.assemble(
        angle, blocks, character.get("profile") or {},
        angle_position=angle_position,
        identity_positions=identity_positions,
        torso_position=torso_position,
    )

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
    return run_routes.create_draft(draft, held) | {"angle": angle["id"]}
