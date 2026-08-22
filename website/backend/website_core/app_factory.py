"""Flask application factory for the website HTTP API."""

import logging
from decimal import Decimal

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

from website_core import config
from website_core.errors import ConfigError, UpstreamError, ValidationError
from website_core.routes.intake import bp as intake_bp
from website_core.routes.newsletter import bp as newsletter_bp

logger = logging.getLogger(__name__)


class DecimalJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


class ApiPathMiddleware:
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
    app.wsgi_app = ApiPathMiddleware(app.wsgi_app)
    app.wsgi_app = BodyLengthMiddleware(app.wsgi_app)

    CORS(
        app,
        resources={r"/api/*": {"origins": config.allowed_origin()}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "OPTIONS"],
    )

    app.register_blueprint(intake_bp)
    app.register_blueprint(newsletter_bp)

    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return "", 204

    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(UpstreamError)
    def handle_upstream_error(error):
        logger.warning("Upstream error: %s", error)
        return jsonify({"error": str(error)}), 502

    @app.errorhandler(ConfigError)
    def handle_config_error(error):
        logger.error("Config error: %s", error)
        return jsonify({"error": str(error)}), 500

    @app.errorhandler(404)
    def handle_not_found(_error):
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
