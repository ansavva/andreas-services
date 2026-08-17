"""Flask application factory for the studio HTTP API."""

import logging

from flask import Flask, jsonify, request
from flask_cors import CORS

from studio_core import config
from studio_core.errors import (
    ConfigError,
    ConflictError,
    NotFoundError,
    UpstreamError,
    ValidationError,
)
from studio_core.routes.browse import bp as browse_bp
from studio_core.routes.manage import bp as manage_bp

logger = logging.getLogger(__name__)


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
    app.wsgi_app = ApiPathMiddleware(app.wsgi_app)

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
