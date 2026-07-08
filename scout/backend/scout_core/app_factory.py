"""Flask application factory for the Scout events HTTP API."""

import importlib
import logging
from decimal import Decimal

from flask import Flask, Response, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

# The routing logic and Lambda entrypoint live in
# scout_core.handlers.lambda.api.api_handler. "lambda" is a reserved keyword, so
# that package can't be reached with a normal `import` statement — load it via
# importlib.
api_routes = importlib.import_module("scout_core.handlers.lambda.api.api_handler")

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


def _event_from_request():
    return {
        "httpMethod": request.method,
        "path": request.path,
        "body": request.get_data(as_text=True) or None,
        "queryStringParameters": request.args.to_dict(flat=True),
        "requestContext": {},
    }


def _flask_response(raw):
    headers = dict(raw.get("headers") or {})
    body = raw.get("body") or ""
    status = raw.get("statusCode", 200)
    if raw.get("isBase64Encoded"):
        import base64  # noqa: PLC0415

        return Response(
            base64.b64decode(body),
            status=status,
            headers=headers,
            content_type=headers.get("Content-Type"),
        )
    return Response(body, status=status, headers=headers, content_type=headers.get("Content-Type"))


def create_app() -> Flask:
    app = Flask(__name__)
    app.json = DecimalJSONProvider(app)
    app.wsgi_app = ApiPathMiddleware(app.wsgi_app)

    CORS(
        app,
        resources={r"/api/*": {"origins": "*"}},
        allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    @app.route("/api", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    @app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    def dispatch(path):
        del path
        return _flask_response(api_routes.route_request(_event_from_request()))

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception("Unhandled error handling %s %s", request.method, request.path)
        return jsonify({"error": str(error)}), 500

    return app


app = create_app()
