"""The reference spec: how a turnaround's prompts are written, as data.

It was `domain/templates/reference_angles.yaml` in the pipeline package, which
meant a wording change was a code change, a review and a release — for prose
whose whole nature is that it gets tuned against what a model actually returned.
Worse, only the CLI could read it: the SPA could not show a person the prompt a
reference render would send, let alone let them fix it.

That is the same argument `POST /api/prompt` already won one tier down for video
prompts, so this is the same answer: the words live in the catalog, both halves
of studio read them from here, and there is one of them.

**Blocks and angles are separate rows on purpose.** A block is shared prose an
angle template cites by name; an angle is one orientation's template plus the
`description` and `tags` that `add-refs --from-run` writes onto a promoted
image. Editing one of either is a single row write, so two people editing
different angles do not overwrite each other and a broken edit breaks one angle
rather than all fourteen.

Hard rule #2 is untouched by everything here. This is what a payload would SAY;
nothing on these routes creates a run, and the approval gate is still on the run
that sends one.
"""

import logging

from flask import Blueprint, g, jsonify

from studio_core.errors import ValidationError
from studio_core.routes import support
from studio_core.services import catalog

logger = logging.getLogger(__name__)

bp = Blueprint("reference_spec", __name__, url_prefix="/api")

#: The groups an angle may belong to. The same two the turnaround shoots in, and
#: the reason this is checked at all is that `group` selects which angles
#: `--group` renders — a typo produces an angle nothing can ever shoot.
GROUPS = ("face", "body")


@bp.get("/reference-spec")
def read_spec():
    """Every block and every angle, in shooting order."""
    held = support.memberships()
    support.member_of(g.library, held)
    return jsonify(catalog.reference_spec(g.library)), 200


@bp.patch("/reference-spec/blocks/<name>")
def put_block(name: str):
    """Write one shared block.

    An overwrite rather than a claim, unlike a phrasebook term: a block IS its
    name, and saving an edit to one is the whole point of the route.

    **PATCH, though it replaces the row.** PUT is the more honest verb for a
    write keyed on a name, and it is not worth what it costs: no route in this
    service has ever used one, so adding it widens `CORS_METHODS` — a
    browser-facing preflight surface for every route in the API — to buy a
    nicer verb on two. `test_every_verb_the_api_accepts_is_in_the_cors_list`
    is what makes that trade visible, and it caught this.
    """
    body = support.body()
    held = support.memberships()
    support.member_of(g.library, held)

    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("text is required")
    if "#" in name:
        # `#` is the key separator, so a name holding one would be
        # indistinguishable from a different row. Refused rather than escaped:
        # a placeholder name never needs one.
        raise ValidationError("a block name may not contain '#'")
    return jsonify(catalog.put_spec_block(g.library, name, text)), 200


@bp.patch("/reference-spec/angles/<angle_id>")
def put_angle(angle_id: str):
    """Write one angle: its group, its prompt template, and how it is described."""
    body = support.body()
    held = support.memberships()
    support.member_of(g.library, held)

    if "#" in angle_id:
        raise ValidationError("an angle id may not contain '#'")
    group = body.get("group")
    if group not in GROUPS:
        raise ValidationError(f"group must be one of {list(GROUPS)}")
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValidationError("prompt is required")
    # `description` and `tags` are not optional, and that is deliberate: they are
    # what `add-refs --from-run` writes onto a promoted image, so an angle
    # missing them promotes undescribed — which is the state the described index
    # exists to prevent, and one nobody notices until a selection by tag comes
    # back short.
    description = body.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError("description is required")
    tags = body.get("tags")
    if not isinstance(tags, list) or not tags or not all(
            isinstance(tag, str) and tag for tag in tags):
        raise ValidationError("tags must be a non-empty list of strings")

    return jsonify(catalog.put_spec_angle(g.library, angle_id, body)), 200


@bp.delete("/reference-spec/angles/<angle_id>")
def delete_angle(angle_id: str):
    held = support.memberships()
    support.member_of(g.library, held)
    catalog.delete_spec_angle(g.library, angle_id)
    return jsonify({"id": angle_id, "deleted": True}), 200


@bp.delete("/reference-spec/blocks/<name>")
def delete_block(name: str):
    """Drop a block.

    **Nothing checks whether an angle still cites it**, and that is not an
    oversight to fix here: a template names its blocks in prose, so the only
    honest check is to assemble every angle and see what fails — which is what
    the assembly does, loudly, naming the placeholder and the angle. Refusing
    the delete on a substring match would also refuse it for a block named in a
    comment.
    """
    held = support.memberships()
    support.member_of(g.library, held)
    catalog.delete_spec_block(g.library, name)
    return jsonify({"name": name, "deleted": True}), 200
