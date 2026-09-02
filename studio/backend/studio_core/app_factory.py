"""Flask application factory for the studio HTTP API."""

import io
import logging

from flask import Flask, g, jsonify, request
from flask_cors import CORS

from studio_core import config
from studio_core.errors import (
    AuthError,
    ConfigError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UpstreamError,
    ValidationError,
)
from studio_core.routes.browse import bp as browse_bp
from studio_core.routes.characters import bp as characters_bp
from studio_core.routes.images import bp as images_bp
from studio_core.routes.libraries import bp as libraries_bp
from studio_core.routes.models import bp as models_bp
from studio_core.routes.movies import bp as movies_bp
from studio_core.routes.nodes import bp as nodes_bp
from studio_core.routes.phrasebook import bp as phrasebook_bp
from studio_core.routes.templates import bp as templates_bp
from studio_core.routes.projects import bp as projects_bp
from studio_core.routes.prompt import bp as prompt_bp
from studio_core.routes.renders import bp as renders_bp
from studio_core.routes.runs import bp as runs_bp
from studio_core.routes.scenes import bp as scenes_bp
from studio_core.services import catalog, identity

logger = logging.getLogger(__name__)

# The header naming which library a request is about. Absent on almost every
# request, because the common case is one library and asking a user to name the
# only thing they have would be a question with one answer.
LIBRARY_HEADER = "X-Studio-Library"

# Paths answered before the caller is known.
#
# `/api/health` is on it for two reasons that happen to agree. The deploy
# workflow smoke-tests the deployed API with a plain unauthenticated GET, so a
# 401 here would fail every deploy; and a health check that needs a token
# reports on Cognito rather than on the Lambda, which is not the question it was
# asked.
UNAUTHENTICATED_PATHS = frozenset({"/api/health"})

# Paths answered for a known caller, about no library in particular.
#
# **Two sets rather than one**, because identifying the caller and scoping the
# request to a library are two decisions and `/api/libraries` (#291) needs
# opposite answers to them. It is the route that says which libraries the caller
# is in, so it cannot require that answer to have been found already — and the
# caller it matters most for is the one in *no* library, whom `_resolve_library`
# refuses with a 403 telling them exactly what they called to ask. Listing it
# above instead would have fixed that by making the only route that reports on a
# specific person the only route needing no proof of who they are.
#
# Unlike the set above, this one names a path before the route serving it lands.
# That is safe here in a way it was not there: an entry that never matches a real
# route leaves an authenticated caller at the 404 they were already getting,
# whereas an unauthentication skip that missed would open a route to strangers.
LIBRARY_UNSCOPED_PATHS = frozenset({"/api/libraries"})

# The verbs and headers this API accepts, and **one of four places that have to
# agree**. The other three are all in `modules/api_gateway`: the MOCK
# integration response that answers the preflight, and the `UNAUTHORIZED` and
# `ACCESS_DENIED` gateway responses beside it — where they are already a single
# `local.cors_methods`, so the split that can actually drift is this list
# against that local.
#
# A verb missing from any of them is a CORS failure no Flask configuration can
# rescue, because the browser's preflight is answered by API Gateway and never
# reaches Flask. The SPA sees a network error with no status: the one failure in
# this service that carries no message at all.
#
# Named constants rather than literals in the `CORS(...)` call below because
# `tests/test_cors_agreement.py` asserts them against both the registered routes
# and the Terraform local — the convention is now a check (#297).
# **PUT is still allowed nowhere, and six entity routes wanted it.**
#
# `docs/ENTITY_MODEL.md` spells them as PUT — a profile, a reference index, a
# default set, a project's characters, a scene's shots, a movie's scenes — and
# every one of them replaces a *collection* rather than merging into one, which
# is exactly what PUT is for. They are PATCH here, for the reason this file
# already gave about saving a text file: adding a verb means changing four
# places at once (this list, the MOCK integration response, and the `UNAUTHORIZED`
# and `ACCESS_DENIED` gateway responses in `modules/api_gateway`), and a verb
# missing from any of them is a CORS failure no Flask configuration can rescue —
# the SPA sees a network error with no status.
#
# **Nothing about the routes changed except the verb.** Same paths, same bodies,
# same status codes, same whole-collection replace semantics. Adopting PUT is a
# one-line change to `local.cors_methods` plus this list, and the routes can move
# the day that lands; until then a verb that works everywhere beats a verb that
# is correct in the abstract and fails in a browser.
CORS_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
CORS_HEADERS = ["Content-Type", "Authorization", LIBRARY_HEADER]


class BodyLengthMiddleware:
    """Restore `CONTENT_LENGTH` from the body that actually arrived.

    **Without this every route that reads a JSON body sees an empty one**, and
    reports the field as missing: `POST /api/objects/move` with a perfectly good
    `{keys, destination}` answers 400 `keys must be a non-empty list`.

    The cause is a seam between two libraries, neither of which is wrong on its
    own. API Gateway's proxy event carries the body as a string and does *not*
    put `Content-Length` in `headers` — verified against the deployed API, whose
    integration request forwards only `{"Content-Type": "application/json"}`.
    Mangum passes those headers through verbatim and never synthesises the
    length. `asgiref.wsgi.WsgiToAsgi` then writes the real body into
    `wsgi.input` but sets `CONTENT_LENGTH` *only* from a `content-length`
    header, so Werkzeug is told the body is zero bytes long and stops reading
    before it starts. The bytes are present the whole way down; the number
    saying how many of them to read is the only thing missing.

    So the length is taken from `wsgi.input` itself rather than from a header,
    which is the one source that cannot disagree with the body. Anything that
    already declared a length keeps it — under `flask run`, gunicorn or Flask's
    test client the header is present and this is a no-op, which is exactly why
    the test suite passed while prod could not write. A non-seekable stream is
    left alone: only the ASGI shim's `SpooledTemporaryFile` is being repaired
    here, and a real chunked upload must not be buffered into memory to measure
    it.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if not environ.get("CONTENT_LENGTH"):
            body = environ.get("wsgi.input")
            if body is not None and getattr(body, "seekable", lambda: False)():
                start = body.tell()
                length = body.seek(0, io.SEEK_END) - start
                body.seek(start)
                if length:
                    environ["CONTENT_LENGTH"] = str(length)
        return self.app(environ, start_response)


class ApiPathMiddleware:
    """Strip an API Gateway stage prefix so routes match either way.

    A custom domain with an empty base path gives `/api/tree`, but a direct
    invoke of the stage gives `/prod/api/tree`. Rewriting here means the
    Blueprint only ever declares one shape.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        idx = path.find("/api/")
        if idx > 0:
            environ["PATH_INFO"] = path[idx:]
        return self.app(environ, start_response)


def _resolve_library(sub: str, requested: str | None) -> str:
    """Which library this request is about, or a refusal saying why not.

    Three cases, in the order they are cheap to be sure of:

    * **The header names one.** Membership is asserted against the caller's own
      rows and a non-member gets 403 — see `errors.ForbiddenError` for why that
      is not a 404.
    * **No header, one membership.** The overwhelmingly common case, and the
      reason the header is optional at all: there is one library, so there is
      nothing to choose between and no UI worth building to choose it.
    * **No header, and the count is not one.** A refusal rather than a guess.
      Picking the first, the oldest or the owned one would each be a rule
      nothing outside this function knows, and every one of them would
      eventually write a node into the wrong library.

    The membership read is one query on one partition (`USER#<sub>`), which is
    what makes doing it per request affordable — see `catalog.libraries_for`.
    """
    memberships = catalog.libraries_for(sub)

    if requested:
        if not any(membership["lib"] == requested for membership in memberships):
            raise ForbiddenError(f"You are not a member of {requested}.")
        return requested

    if len(memberships) == 1:
        return memberships[0]["lib"]

    if not memberships:
        # Authenticated, and a member of nothing. **Not the 400 below**: there
        # is no header this caller could send that would work, so "name one" is
        # an instruction they cannot follow. The pool is admin-create-only, so
        # this is an account someone created and never added to a library — a
        # provisioning gap, and 403 is the status that says the request was
        # understood and refused rather than malformed.
        raise ForbiddenError("You are not a member of any library.")

    # Naming the choice, not just the header: these are the caller's own
    # libraries, so listing them leaks nothing they cannot already read, and it
    # turns the 400 into something answerable from curl without a second round
    # trip to find out what the ids are.
    choices = ", ".join(sorted(membership["lib"] for membership in memberships))
    raise ValidationError(
        "You are a member of more than one library — name one in the "
        f"{LIBRARY_HEADER} header: {choices}"
    )


def create_app() -> Flask:
    app = Flask(__name__)
    app.wsgi_app = ApiPathMiddleware(BodyLengthMiddleware(app.wsgi_app))

    # The write verbs are listed here *and* on the MOCK preflight and the two
    # gateway responses in `modules/api_gateway`. All four have to agree: the
    # browser's preflight is answered by API Gateway, not by Flask, so a method
    # missing there is a CORS failure the Flask config cannot rescue.
    #
    # `X-Studio-Library` is subject to the same four-file agreement, and is
    # added here and in `modules/api_gateway`'s `cors_headers` in the same
    # change that starts reading it. A custom request header the browser has not
    # been told is allowed fails the preflight, and the SPA sees a network error
    # with no status — the one failure mode in this service that carries no
    # message at all.
    CORS(
        app,
        resources={r"/api/*": {"origins": config.allowed_origin()}},
        allow_headers=CORS_HEADERS,
        methods=CORS_METHODS,
    )

    app.register_blueprint(browse_bp)
    # Its own blueprint rather than a fourth route in `browse`: it is the one
    # route that is authenticated without being about a library's contents, and
    # `routes/libraries.py` explains what that costs the request hook.
    app.register_blueprint(libraries_bp)
    # The file layer, kept apart from `browse` for the reason `routes/nodes.py`
    # gives: one returns node records, the other returns a folder ready to draw.
    # `routes/manage.py` used to sit beside it holding the same verbs addressed
    # by name path; the entity model retired the second addressing scheme and the
    # file with it.
    app.register_blueprint(nodes_bp)
    # The five entity kinds and the phrasebook, one blueprint each. Split by
    # entity rather than by verb because that is how they are read: everything
    # about a character is in one file, and a route that has to know about two
    # entities (a run naming its project) imports the other module's resolver
    # rather than growing a second copy of it.
    app.register_blueprint(characters_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(runs_bp)
    app.register_blueprint(scenes_bp)
    app.register_blueprint(movies_bp)
    app.register_blueprint(phrasebook_bp)
    # How a reference prompt is written, as rows. Its own blueprint rather
    # than part of `characters` because the spec belongs to the LIBRARY: one
    # set of angles describes every character in it.
    app.register_blueprint(templates_bp)
    # Drafting a character's reference angles. It writes RUNS, so it could
    # live in `runs`; it is here because what it is ABOUT is a character's
    # identity, and it calls `runs.create_draft` rather than reimplementing
    # what a draft is.
    app.register_blueprint(models_bp)
    # The two halves of what used to be local media processing. `renders`
    # enqueues onto the render queue and reports on a job row; `images` does
    # the two Pillow-only operations in this process, because a queue round
    # trip costs more than the work — see `routes/images.py`.
    app.register_blueprint(renders_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(prompt_bp)

    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return "", 204

    @app.before_request
    def resolve_caller():
        """Put the caller and their library on `g` before any route runs.

        Here rather than in each route because an authorization check a route
        can forget is one a route will eventually forget — and the route that
        forgets is the one that writes. Everything below this line may assume
        `g.caller_sub` and `g.library` exist — with `g.library` **`None`** on a
        `LIBRARY_UNSCOPED_PATHS` path, where the question being asked is about no
        library in particular. It is assigned there rather than left unset for
        exactly that reason: the promise this hook makes is that the attribute
        exists, so an unscoped route reads a library of `None` instead of raising
        `AttributeError` three frames down, in a route that never mentioned `g`.

        **OPTIONS is tested for again**, even though `handle_preflight` above
        already answers every preflight and Flask stops at the first
        `before_request` to return something. That short-circuit is an ordering
        guarantee held by two adjacent registrations, and the cost of losing it
        is a 401 on a preflight, which the browser reports to the SPA as a
        network error with no status. Cheap to state; expensive to rediscover.

        **This also runs for a path no route matches**, because Flask resolves
        routing inside `dispatch_request`, after `preprocess_request` — so an
        unauthenticated `GET /api/nope` is 401 rather than 404. Left that way on
        purpose: a stranger enumerating the route table is not owed the
        difference between a path that exists and one that does not.
        """
        if request.method == "OPTIONS" or request.path in UNAUTHENTICATED_PATHS:
            return None
        g.caller_sub = identity.caller_sub(request.headers.get("Authorization"))
        g.library = (
            None
            if request.path in LIBRARY_UNSCOPED_PATHS
            else _resolve_library(g.caller_sub, request.headers.get(LIBRARY_HEADER))
        )
        return None

    # The message is deliberately coarse and never carries the token — see
    # `errors.AuthError`. Nothing is logged either: an unauthenticated call is a
    # normal event on a public endpoint, not an incident.
    @app.errorhandler(AuthError)
    def handle_auth_error(error):
        return jsonify({"error": str(error)}), 401

    # Nothing is logged here either, for the reason above: a caller reaching a
    # library they are not in is a normal event once libraries are shared, and
    # the row that proves it is not something to copy into CloudWatch.
    @app.errorhandler(ForbiddenError)
    def handle_forbidden_error(error):
        return jsonify({"error": str(error)}), 403

    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(NotFoundError)
    def handle_not_found_error(error):
        return jsonify({"error": f"No such object: {error}"}), 404

    # A sibling of ValidationError rather than a subclass, so this handler is
    # the one Flask picks — the message is already user-facing ("'x' already
    # exists here") and the status is what tells the UI to keep the rename field
    # open instead of closing it.
    @app.errorhandler(ConflictError)
    def handle_conflict_error(error):
        return jsonify({"error": str(error)}), 409

    @app.errorhandler(UpstreamError)
    def handle_upstream_error(error):
        logger.warning("Upstream error: %s", error)
        return jsonify({"error": str(error)}), 502

    @app.errorhandler(ConfigError)
    def handle_config_error(error):
        logger.error("Config error: %s", error)
        return jsonify({"error": str(error)}), 500

    @app.errorhandler(404)
    def handle_route_not_found(_error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception(
            "Unhandled error handling %s %s",
            request.method,
            request.path,
            exc_info=error,
        )
        return jsonify({"error": "Internal error"}), 500

    return app


app = create_app()
