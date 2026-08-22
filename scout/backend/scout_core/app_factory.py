"""Flask application factory for the Scout events HTTP API."""

import logging
from decimal import Decimal

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from scout_core.routes.deleted import bp as deleted_bp
from scout_core.routes.events import bp as events_bp
from scout_core.routes.labels import bp as labels_bp
from scout_core.routes.locations import bp as locations_bp
from scout_core.routes.notifications import bp as notifications_bp
from scout_core.routes.public import bp as public_bp
from scout_core.routes.settings import bp as settings_bp
from scout_core.routes.sources import bp as sources_bp

logger = logging.getLogger(__name__)

_BLUEPRINTS = (
    public_bp, sources_bp, events_bp, locations_bp,
    labels_bp, settings_bp, notifications_bp, deleted_bp,
)


class DecimalJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


class ApiPathMiddleware:
    """Strip an API Gateway stage / base-path prefix so routing always sees
    a path starting at ``/api/`` (prod, the ``{proxy+}`` catch-all, PR bases)."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        idx = path.find("/api/")
        if idx > 0:
            environ["PATH_INFO"] = path[idx:]
        return self.app(environ, start_response)


class BodyLengthMiddleware:
    """Set ``CONTENT_LENGTH`` from the body when the request carries no header.

    API Gateway's proxy event does not reliably put ``Content-Length`` in
    ``headers``. Mangum forwards the event's headers verbatim and never
    synthesises the length, and ``asgiref.wsgi`` derives ``CONTENT_LENGTH``
    only from a ``content-length`` header — so Werkzeug is told the body is
    zero bytes and reads none of it. Every write then answers 400 naming its
    own fields as missing, for a request that did send them.

    ``wsgi.input`` is a ``BytesIO`` holding the whole body by then, so the
    length is already known here. The seekable check keeps this a no-op under
    a server that streams the request instead of buffering it.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if not environ.get("CONTENT_LENGTH"):
            stream = environ.get("wsgi.input")
            if stream is not None and getattr(stream, "seekable", lambda: False)():
                start = stream.tell()
                length = stream.seek(0, 2) - start
                stream.seek(start)
                if length:
                    environ["CONTENT_LENGTH"] = str(length)
        return self.app(environ, start_response)


def create_app() -> Flask:
    app = Flask(__name__)
    app.json = DecimalJSONProvider(app)
    # Match paths with or without a trailing slash (no 308 redirects) — the
    # collection routes are registered without one.
    app.url_map.strict_slashes = False
    app.wsgi_app = ApiPathMiddleware(app.wsgi_app)
    app.wsgi_app = BodyLengthMiddleware(app.wsgi_app)

    CORS(
        app,
        resources={r"/api/*": {"origins": "*"}},
        allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    for bp in _BLUEPRINTS:
        app.register_blueprint(bp)

    # Services signal bad input by raising: a missing required field surfaces as
    # KeyError, an invalid value as ValueError. Map both to 400.
    @app.errorhandler(KeyError)
    def handle_missing_field(error):
        return jsonify({"error": f"missing field: {error}"}), 400

    @app.errorhandler(ValueError)
    def handle_bad_value(error):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        if isinstance(error, HTTPException):
            return jsonify({"error": error.description}), error.code
        logger.exception("Unhandled error handling %s %s", request.method, request.path)
        return jsonify({"error": str(error)}), 500

    return app


app = create_app()
