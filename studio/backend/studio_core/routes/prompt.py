"""Assemble and validate a structured video prompt.

One route over `services/prompt.py`. It exists because the six hundred lines of
prompting judgement behind it were reachable only from a terminal: the SPA could
not offer a single one of those checks, and neither could anything else that
might come to author a shot.

**A pure function over a body, and the only route here that writes nothing.**
Nothing is stored, no run is created, nothing bills. That is what makes it safe
to call on every keystroke of an editor, and it is why the verb is POST despite
being a read — the input is a document, not a query string.

Hard rule #2 is untouched. This says what a payload *would* be; the approval gate
is on the run that sends one.
"""

import logging

from flask import Blueprint, g, jsonify

from studio_core.errors import ValidationError
from studio_core.routes import support
from studio_core.services import catalog
from studio_core.services import prompt as prompt_service

logger = logging.getLogger(__name__)

bp = Blueprint("prompt", __name__, url_prefix="/api")

#: What `emit` may ask for. `prompt` is the serialized string alone, `input` the
#: provider's parameter object alone, `both` the pair — the shapes the CLI's
#: `--emit` already had, kept because they are what a person pastes.
EMIT = ("both", "input", "prompt")


@bp.post("/prompt")
def assemble():
    """Take a structured object, answer with the prompt, the input and the warnings.

    **Errors come back 200 with an `errors` list, not as a 400.** An editor
    asking "what is wrong with this so far" gets an answer it can draw, and a
    half-written prompt is the ordinary case rather than a bad request. The one
    thing that IS a 400 is a body this cannot read at all — an unknown engine, or
    an `object` that is not an object — because there is nothing to say about it.
    """
    body = support.body()

    engine = body.get("engine") or "seedance"
    if engine not in prompt_service.engines():
        raise ValidationError(
            f"unknown engine {engine!r} — "
            f"expected one of {', '.join(sorted(prompt_service.engines()))}"
        )

    obj = body.get("object")
    if not isinstance(obj, dict):
        raise ValidationError("object must be an object")

    emit = body.get("emit") or "both"
    if emit not in EMIT:
        raise ValidationError(f"emit must be one of {', '.join(EMIT)}")

    overrides = body.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValidationError("overrides must be an object")

    return jsonify(prompt_service.assemble(
        obj, engine, emit=emit, compact=bool(body.get("compact")),
        overrides=overrides or {},
        # Injected, so `services/prompt.py` imports neither Flask nor boto3 and
        # can be loaded by path by the pipeline's fake. See its docstring.
        terms_lookup=lambda model: catalog.terms(g.library, model),
    )), 200
