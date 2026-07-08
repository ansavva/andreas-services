"""Flask application factory for the website HTTP API."""

import logging
from decimal import Decimal

from flask import Blueprint, Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

from website_core import config
from website_core.errors import ConfigError, UpstreamError, ValidationError
from website_core.services import intake, newsletter

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


api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.post("/intake")
def create_submission():
    body = request.get_json(silent=True) or {}
    item = intake.create_submission(body, source_page=body.get("source_page"))
    return jsonify(item), 201


@api_bp.post("/subscribe")
def subscribe():
    body = request.get_json(silent=True) or {}
    return jsonify(newsletter.subscribe(body)), 201


@api_bp.get("/admin/submissions")
def list_submissions():
    return jsonify(
        intake.list_submissions(
            limit=request.args.get("page_size", 50),
            cursor=request.args.get("cursor"),
        )
    ), 200


def create_app() -> Flask:
    app = Flask(__name__)
    app.json = DecimalJSONProvider(app)
    app.wsgi_app = ApiPathMiddleware(app.wsgi_app)

    CORS(
        app,
        resources={r"/api/*": {"origins": config.allowed_origin()}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "OPTIONS"],
    )

    app.register_blueprint(api_bp)

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
