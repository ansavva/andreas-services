"""The template library: how a prompt is written, as data.

It was `domain/templates/reference_angles.yaml` in the pipeline package, which
meant a wording change was a code change, a review and a release — for prose
whose whole nature is that it gets tuned against what a model actually returned.
Worse, only the CLI could read it: the SPA could not show a person the prompt a
reference render would send, let alone let them fix it.

That is the same argument `POST /api/prompt` already won one tier down for video
prompts, so this is the same answer: the words live in the catalog, both halves
of studio read them from here, and there is one of them.

**Blocks and templates are separate rows on purpose.** A block is shared prose a
template cites by name; a template is a prompt plus the `description` and `tags`
a person starts from when the image it makes becomes identity. Editing either is
a single row write, so two people editing two templates do not overwrite each
other and a broken edit breaks one rather than all fourteen.

**These were reference ANGLES**, and the narrowing was the problem: they held one
orientation of one character's standard set, they carried a `group` that had to
be `face` or `body`, and only a turnaround could use one. A template is a prompt
a person wrote, picked for a run — which is what every one of those angles
already was, with a fourteen-at-a-time fan-out on top of it.

Hard rule #2 is untouched by everything here. This is what a payload would SAY;
nothing on these routes creates a run, let alone sends one.
"""

import logging

from flask import Blueprint, g, jsonify

import re

from studio_core.errors import ValidationError
from studio_core.routes import support
from studio_core.services import catalog

logger = logging.getLogger(__name__)

bp = Blueprint("templates", __name__, url_prefix="/api")


@bp.get("/templates")
def read_templates():
    """Every block and every template, by name."""
    held = support.memberships()
    support.member_of(g.library, held)
    return jsonify(catalog.templates(g.library)), 200


#: What a block may be called. The same rule a Python identifier follows,
#: because `{block.<name>}` resolves by attribute access.
BLOCK_NAME = re.compile(r"[a-z_][a-z0-9_]*")


@bp.patch("/templates/blocks/<name>")
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
    if not BLOCK_NAME.fullmatch(name):
        # **A block is cited as `{block.<name>}`, and a dot in a format field is
        # attribute access** — so a name that is not a Python identifier is a
        # block nothing can ever cite. `#` was the only thing refused here, and
        # it let somebody create `2fast` or `a-b`: rows that exist, appear in the
        # menu, and fail the moment a template names them.
        raise ValidationError(
            "a block name must be lowercase letters, digits and underscores, "
            "starting with a letter or underscore — it is cited as "
            "{block.<name>}, and anything else cannot be")
    return jsonify(catalog.put_spec_block(g.library, name, text)), 200


@bp.patch("/templates/<template_id>")
def put_template(template_id: str):
    """Write one template: its name, prompt, and how its output is described.

    **Keyed on a UUID, with the name as an ordinary field**, which is what every
    entity in this table does. It was briefly keyed on the name, on the grounds
    that nothing points at a template so a rename strands nothing — a judgement
    about a fact that changes, since "which template did this run start from" is
    an obvious field a name key would strand.

    A rename is therefore a field write and nothing else. Names are not unique
    and are not claimed: identity is the id, so two templates called the same
    thing are a display problem rather than an ambiguity.

    **`group` is not a field any more.** It had to be `face` or `body`, because
    it selected which angles a `--group` turnaround rendered and it chose the
    variant of `build` and `must` the fill used. Nothing shoots a set, and the
    variant is named in the prompt — `{character.1.build.face}` — so the column
    was a second place to say something the template already says.
    """
    body = support.body()
    held = support.memberships()
    support.member_of(g.library, held)

    if "#" in template_id or "/" in template_id:
        raise ValidationError("a template id may not contain '#' or '/'")

    # **A PATCH may carry one field.** It required all of them, which made a
    # rename impossible to send on its own — the caller had to re-state the
    # prompt, the description and the tags to change the name, and a caller that
    # sent only the name got a 400 and a row left as it was. Worse than the
    # refusal: the obvious retry is to send the whole body, and a body assembled
    # from memory overwrites the prose with whatever the caller last knew.
    #
    # So the fields fall back to what is stored, and they are required only when
    # there is nothing stored to fall back to — which is exactly a create.
    stored = next((each for each in catalog.templates(g.library)["templates"]
                   if each["id"] == template_id), None)
    body = {**(stored or {}), **body}
    body["name"] = catalog.clean_template_name(body.get("name"))

    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValidationError("prompt is required")
    # `description` and `tags` are not optional, and that is deliberate: they are
    # what a promotion starts from when the image this makes becomes identity, so
    # a template missing them promotes undescribed — and an undescribed image is
    # invisible to whoever picks a set, which nobody notices until a selection by
    # tag comes back short.
    description = body.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError("description is required")
    tags = body.get("tags")
    if not isinstance(tags, list) or not tags or not all(
            isinstance(tag, str) and tag for tag in tags):
        raise ValidationError("tags must be a non-empty list of strings")

    return jsonify(catalog.put_template(g.library, template_id, body)), 200


@bp.delete("/templates/<template_id>")
def delete_template(template_id: str):
    held = support.memberships()
    support.member_of(g.library, held)
    catalog.delete_template(g.library, template_id)
    return jsonify({"id": template_id, "deleted": True}), 200


@bp.delete("/templates/blocks/<name>")
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
