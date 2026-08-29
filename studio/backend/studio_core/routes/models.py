"""The model registry, served.

Two read routes over `services/registry.py`. They exist so there is one copy of
the registry at *runtime* as well as one in the repo: the pipeline reads them
instead of a file it shipped, and `GET /api/characters/<id>/selection` measures
against the same entries rather than the three hardcoded caps it used to carry.

**Unauthenticated in everything but form.** These sit behind the same Cognito
authorizer as every other `/api` route, because the gateway applies it to the
whole stage — but nothing here reads `g.library` or the caller's memberships, and
two accounts get byte-identical answers. The registry is a property of the
service, not of a library: which models exist is the same question whoever asks.

**Read-only, and that is a rule rather than a gap.** `studio add-model` and
`studio models refresh` write `models.json` in the repo, reviewed in a PR, and
the API serves what shipped. A write route would make the deployed registry
divergeable from the committed one, which is the drift this move exists to end —
and it would put the Replicate schema fetch, which is what both of those commands
are really doing, inside a request a person is waiting on.
"""

import logging

from flask import Blueprint, jsonify

from studio_core.services import registry

logger = logging.getLogger(__name__)

bp = Blueprint("models", __name__, url_prefix="/api")


@bp.get("/models")
def list_models():
    """Every entry, keyed by registry name.

    A map rather than a bare array, unlike `/api/libraries`: every caller of this
    is looking a model up by the key it was given on a command line, and handing
    back a list would make each of them build the same index. The key is also
    inside each entry, so a caller that does iterate does not lose it.
    """
    return jsonify({"models": registry.all()}), 200


@bp.get("/models/<path:name>")
def get_model(name: str):
    """One entry, by registry key or alias.

    `<path:name>` rather than `<name>`, because a caller may reasonably address
    an entry by its Replicate id — `openai/gpt-image-2` — and a plain converter
    would 404 on the slash before this function ran. Both spellings resolve.
    """
    entry = registry.find(name) or registry.by_model_id(name)
    if entry is None:
        # `NotFoundError` via the same shape every other 404 here uses, rather
        # than a bare 404: a client matching on the body should not have to
        # special-case this route.
        from studio_core.errors import NotFoundError

        raise NotFoundError(name)
    return jsonify(entry), 200
