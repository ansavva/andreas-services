from __future__ import annotations

import logging

from flask import Flask, jsonify

from mailer.api.dependencies import ApiDependencies
from mailer.api.routes.attachments import blueprint as attachments_blueprint
from mailer.api.routes.messages import blueprint as messages_blueprint
from mailer.core.errors import (
    AuthorizationError,
    ConflictError,
    MailerError,
    RetryableError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class BodyLengthMiddleware:
    """Set ``CONTENT_LENGTH`` from the body when the request carries no header.

    API Gateway's proxy event does not reliably put ``Content-Length`` in
    ``headers``. Mangum forwards the event's headers verbatim and never
    synthesises the length, and ``asgiref.wsgi`` derives ``CONTENT_LENGTH``
    only from a ``content-length`` header — so Werkzeug is told the body is
    zero bytes and reads none of it. ``json_body`` then rejects the request as
    "must be a JSON object" for a caller that did send one.

    ``wsgi.input`` is a ``BytesIO`` holding the whole body by then, so the
    length is already known here. The seekable check keeps this a no-op under
    gunicorn, which streams the request instead of buffering it.
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


def create_app(dependencies: ApiDependencies) -> Flask:
    app = Flask(__name__)
    app.wsgi_app = BodyLengthMiddleware(app.wsgi_app)
    app.extensions["mailer_dependencies"] = dependencies
    app.register_blueprint(attachments_blueprint)
    app.register_blueprint(messages_blueprint)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(AuthorizationError)
    def authorization_error(error: AuthorizationError):
        return jsonify({"error": "Forbidden", "message": str(error)}), 403

    @app.errorhandler(ConflictError)
    def conflict_error(error: ConflictError):
        return jsonify({"error": "Conflict", "message": str(error)}), 409

    @app.errorhandler(ValidationError)
    def validation_error(error: ValidationError):
        return jsonify({"error": "ValidationError", "message": str(error)}), 400

    @app.errorhandler(RetryableError)
    def retryable_error(_error: RetryableError):
        logger.exception("retryable Mailer admission failure")
        return jsonify({"error": "Unavailable", "message": "admission is unavailable"}), 503

    @app.errorhandler(MailerError)
    def mailer_error(error: MailerError):
        return jsonify({"error": error.__class__.__name__, "message": str(error)}), 400

    @app.errorhandler(Exception)
    def unexpected_error(_error: Exception):
        logger.exception("unexpected Mailer API failure")
        return jsonify({"error": "InternalError", "message": "request failed"}), 500

    return app
