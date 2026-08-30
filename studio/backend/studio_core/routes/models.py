"""The model registry, served.

Four read routes: two over `services/registry.py`, and two that proxy the
provider's own live schema and README. They exist so there is one copy of
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
divergeable from the committed one, which is the drift this move exists to end.

**Two of the routes below fetch a LIVE schema, and this docstring used to argue
against exactly that.** It said a schema fetch belongs nowhere near "a request a
person is waiting on" — which was an argument against making the *write* a route
and has been read since as an argument against the read. The read had to come
here anyway, for a plainer reason: after generation moved into the API the
pipeline holds no Replicate token at all, so `studio models show`, `studio models
refresh` and `studio add-model` had a choice between reaching the provider
through this service or keeping a provider credential on every developer's
machine for three commands that never spend anything. The credential is the
larger cost.

So `GET /api/models/<name>/schema` and `/readme` proxy the provider, and what the
old objection was really about is preserved: **nothing here writes.** The schema
is fetched, returned, and forgotten; `models.json` is still only ever changed by
a reviewed commit.
"""

import logging

from flask import Blueprint, jsonify

from studio_core.clients import replicate
from studio_core.errors import NotFoundError
from studio_core.services import registry, schema

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


def _model_id(name: str) -> str:
    """The Replicate `owner/name` behind whatever the caller typed.

    A registry key, an alias, or a Replicate id already — and an id for a model
    that is not registered at all, which is the case `studio add-model` and
    `studio run owner/name` exist for. The only refusal is a bare word that
    resolves to nothing, because that cannot be a model id: it has no slash.

    **`<path:name>` is greedy and the two live routes still win.** Werkzeug sorts
    rules by static weight rather than by registration order, so
    `/api/models/openai/gpt-image-2/schema` matches the `/schema` rule with
    `name="openai/gpt-image-2"` and not the bare rule with `name` swallowing the
    suffix. Verified rather than assumed, because the failure would be silent: a
    schema request answered with a registry entry.
    """
    entry = registry.find(name) or registry.by_model_id(name)
    model_id = entry["model"] if entry else name
    if "/" not in model_id:
        raise NotFoundError(name)
    return model_id


@bp.get("/models/<path:name>/schema")
def model_schema(name: str):
    """The model's LIVE input schema, fetched from Replicate on every call.

    **Live and not the snapshot**, which is the entry's `snapshot` field and is
    served by the route below as part of the entry. The two answer different
    questions: the snapshot is what `studio models refresh` recorded into the
    repo and may be months old, and this is what the provider will accept today.
    A payload is validated against this one at submit time, in
    `services/schema.py`, which is why a stale snapshot is survivable.

    `props` is the raw property map and `schemas` the sibling components an enum
    may hide behind a `$ref`. **Raw, and not distilled**: the condensed
    enum/range form that lands in `models.json` is computed by the pipeline,
    which is what owns that file. This route reads the provider and stops.

    Unregistered models resolve too: `?model=owner/name` is not needed, the path
    takes either spelling, and a model absent from the registry is still fetched.
    That is what `studio add-model` and `studio run owner/name` are for — both
    ask about a model precisely because it is not registered yet.
    """
    model_id = _model_id(name)
    props, schemas = schema.fetch(model_id)
    return jsonify({"model": model_id, "props": props, "schemas": schemas}), 200


@bp.get("/models/<path:name>/readme")
def model_readme(name: str):
    """The model's README as raw markdown, wrapped in JSON.

    Read by `studio add-model`, which infers a registry entry from prose the
    schema does not carry — which extensions a model really accepts, whether a
    start frame excludes the reference list. The inference stays in the CLI,
    because what it produces is a repo file somebody reviews.

    Wrapped rather than served as `text/markdown` so every response from this API
    is JSON and `apis/client.ts` needs no second code path for one route.
    """
    model_id = _model_id(name)
    return jsonify({"model": model_id, "readme": replicate.model_readme(model_id)}), 200


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
        raise NotFoundError(name)
    return jsonify(entry), 200
