from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import structlog

from storybook_core.config import AppConfig
from storybook_core.utils.http.identity import CognitoJWTValidator, require_cognito_auth
from storybook_core.repositories.dynamodb import init_db
from storybook_core.utils.logging.logger import configure_logging
from storybook_core.routes.image import bp as image_bp
from storybook_core.routes.model import bp as model_bp
from storybook_core.routes.model_project import bp as model_project_bp
from storybook_core.routes.story_project import bp as story_project_bp
from storybook_core.routes.child_profile import bp as child_profile_bp
from storybook_core.routes.character import bp as character_bp
from storybook_core.routes.model_chat import bp as model_chat_bp
from storybook_core.routes.story_chat import bp as story_chat_bp
from storybook_core.routes.story_page import bp as story_page_bp
from storybook_core.routes.config import bp as config_bp
from storybook_core.routes.generation_history import bp as generation_history_bp
from storybook_core.routes.user_profile import bp as user_profile_bp

load_dotenv()
configure_logging()
logger = structlog.get_logger(__name__)

_auth_configured = False


class BodyLengthMiddleware:
    """Set CONTENT_LENGTH from the body when the request carries no header.

    API Gateway's proxy event does not reliably put Content-Length in
    ``headers``. Mangum forwards the event's headers verbatim and never
    synthesises the length, and ``asgiref.wsgi`` derives CONTENT_LENGTH only
    from a ``content-length`` header — so Werkzeug is told the body is zero
    bytes and reads none of it. ``request.get_json()`` then fails on a request
    that did send a body.

    ``wsgi.input`` is a BytesIO holding the whole body by then, so the length
    is already known here. The seekable check keeps this a no-op under a
    server that streams the request instead of buffering it.
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
    # Initialize Cognito authentication
    cognito_validator = CognitoJWTValidator(
        region=AppConfig.AWS_REGION,
        user_pool_id=AppConfig.AWS_COGNITO_USER_POOL_ID,
        app_client_id=AppConfig.AWS_COGNITO_APP_CLIENT_ID,
    )

    app = Flask(__name__)
    app.wsgi_app = BodyLengthMiddleware(app.wsgi_app)
    app.logger = structlog.get_logger("flask.app")
    app.config.from_object(AppConfig)

    # Initialize database connection
    init_db(app)

    # Set up CORS - allow frontend origin
    CORS(
        app,
        resources={r"/api/*": {"origins": AppConfig.APP_URL}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    global _auth_configured
    if not _auth_configured:
        # Apply Cognito authentication to blueprints once.
        @image_bp.before_request
        @require_cognito_auth(cognito_validator)
        def image_authentication():
            pass

        @model_bp.before_request
        @require_cognito_auth(cognito_validator)
        def model_authentication():
            pass

        @model_project_bp.before_request
        @require_cognito_auth(cognito_validator)
        def model_project_authentication():
            pass

        @story_project_bp.before_request
        @require_cognito_auth(cognito_validator)
        def story_project_authentication():
            pass

        @child_profile_bp.before_request
        @require_cognito_auth(cognito_validator)
        def child_profile_authentication():
            pass

        @character_bp.before_request
        @require_cognito_auth(cognito_validator)
        def character_authentication():
            pass

        @story_chat_bp.before_request
        @require_cognito_auth(cognito_validator)
        def story_chat_authentication():
            pass

        @model_chat_bp.before_request
        @require_cognito_auth(cognito_validator)
        def model_chat_authentication():
            pass

        @story_page_bp.before_request
        @require_cognito_auth(cognito_validator)
        def story_page_authentication():
            pass

        @config_bp.before_request
        @require_cognito_auth(cognito_validator)
        def config_authentication():
            pass

        @generation_history_bp.before_request
        @require_cognito_auth(cognito_validator)
        def generation_history_authentication():
            pass

        @user_profile_bp.before_request
        @require_cognito_auth(cognito_validator)
        def user_profile_authentication():
            pass

        _auth_configured = True

    # Register Blueprints (each carries its own /api/* url_prefix)
    app.register_blueprint(image_bp)
    app.register_blueprint(model_bp)
    app.register_blueprint(model_project_bp)
    app.register_blueprint(story_project_bp)
    app.register_blueprint(child_profile_bp)
    app.register_blueprint(character_bp)
    app.register_blueprint(story_chat_bp)
    app.register_blueprint(model_chat_bp)
    app.register_blueprint(story_page_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(generation_history_bp)
    app.register_blueprint(user_profile_bp)

    # Capture unexpected exceptions and log details to CloudWatch.
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception(
            "Unhandled exception while processing request",
            path=request.path,
            method=request.method,
            user_id=getattr(request, "cognito_user_id", None),
        )
        return jsonify({"error": "Internal server error"}), 500

    # Define public endpoints
    @app.route("/")
    def index():
        return jsonify({"status": "ok"}), 200

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"}), 200

    return app


app = create_app()
