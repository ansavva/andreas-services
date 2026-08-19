"""Flask application factory for the studio HTTP API."""

import io
import logging

from flask import Flask, jsonify, request
from flask_cors import CORS

from studio_core import config
from studio_core.errors import (
    AuthError,
    ConfigError,
    ConflictError,
    NotFoundError,
    UpstreamError,
    ValidationError,
)
from studio_core.routes.browse import bp as browse_bp
from studio_core.routes.manage import bp as manage_bp

logger = logging.getLogger(__name__)


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


def create_app() -> Flask:
    app = Flask(__name__)
    app.wsgi_app = ApiPathMiddleware(BodyLengthMiddleware(app.wsgi_app))

    # The write verbs are listed here *and* on the MOCK preflight and the two
    # gateway responses in `modules/api_gateway`. All four have to agree: the
    # browser's preflight is answered by API Gateway, not by Flask, so a method
    # missing there is a CORS failure the Flask config cannot rescue.
    CORS(
        app,
        resources={r"/api/*": {"origins": config.allowed_origin()}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    )

    app.register_blueprint(browse_bp)
    app.register_blueprint(manage_bp)

    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return "", 204

    # The message is deliberately coarse and never carries the token — see
    # `errors.AuthError`. Nothing is logged either: an unauthenticated call is a
    # normal event on a public endpoint, not an incident.
    @app.errorhandler(AuthError)
    def handle_auth_error(error):
        return jsonify({"error": str(error)}), 401

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
