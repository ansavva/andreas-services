"""Flask application factory for the classroom HTTP API."""

import logging
from decimal import Decimal

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from classroom_core.auth import Unauthenticated
from classroom_core.routes.pages import bp as pages_bp
from classroom_core.routes.public import bp as public_bp

logger = logging.getLogger(__name__)

_BLUEPRINTS = (public_bp, pages_bp)


class DecimalJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


class ApiPathMiddleware:
    """Strip an API Gateway stage / base-path prefix so routing always sees a
    path starting at ``/api/``."""

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
    ``headers``; Mangum forwards headers verbatim and ``asgiref.wsgi`` derives
    ``CONTENT_LENGTH`` only from that header. Without this, Werkzeug is told the
    body is zero bytes, and every write answers 400 naming its own fields as
    missing for a request that did send them.
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

    @app.errorhandler(Unauthenticated)
    def handle_unauthenticated(error):
        return jsonify({"error": str(error)}), 401

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
