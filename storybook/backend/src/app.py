from dotenv import load_dotenv
import os
from functools import wraps
from flask import Flask, jsonify, request
from flask_cors import CORS

from src.config import Config
from src.cognito_validator import CognitoJWTValidator, require_cognito_auth
from src.data.database import init_db
from src.logging_config import configure_logging
from src.controllers.image_controller import image_controller
from src.controllers.model_controller import model_controller
from src.controllers.model_project_controller import model_project_controller
from src.controllers.story_project_controller import story_project_controller
from src.controllers.child_profile_controller import child_profile_controller
from src.controllers.character_controller import character_controller
from src.controllers.chat_controller import chat_controller
from src.controllers.story_page_controller import story_page_controller
from src.controllers.config_controller import config_controller
from src.controllers.generation_history_controller import generation_history_controller
from src.controllers.user_profile_controller import user_profile_controller

load_dotenv()
configure_logging()

# Initialize Cognito authentication
cognito_validator = CognitoJWTValidator(
    region=os.getenv('AWS_COGNITO_REGION', 'us-east-1'),
    user_pool_id=os.getenv('AWS_COGNITO_USER_POOL_ID'),
    app_client_id=os.getenv('AWS_COGNITO_APP_CLIENT_ID')
)

# Initialize Flask app and configuration
app = Flask(__name__)
app.config.from_object(Config)

# Initialize database connection
init_db(app)

# Set up CORS - allow frontend origin
CORS(app,
     resources={r"/api/*": {"origins": os.getenv('APP_URL', 'http://localhost:5173')}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# Apply Cognito authentication to blueprints
@image_controller.before_request
@require_cognito_auth(cognito_validator)
def image_authentication():
    pass

@model_controller.before_request
@require_cognito_auth(cognito_validator)
def model_authentication():
    pass

@model_project_controller.before_request
@require_cognito_auth(cognito_validator)
def model_project_authentication():
    pass

@story_project_controller.before_request
@require_cognito_auth(cognito_validator)
def story_project_authentication():
    pass

@child_profile_controller.before_request
@require_cognito_auth(cognito_validator)
def child_profile_authentication():
    pass

@character_controller.before_request
@require_cognito_auth(cognito_validator)
def character_authentication():
    pass

@chat_controller.before_request
@require_cognito_auth(cognito_validator)
def chat_authentication():
    pass

@story_page_controller.before_request
@require_cognito_auth(cognito_validator)
def story_page_authentication():
    pass

@config_controller.before_request
@require_cognito_auth(cognito_validator)
def config_authentication():
    pass

@generation_history_controller.before_request
@require_cognito_auth(cognito_validator)
def generation_history_authentication():
    pass

@user_profile_controller.before_request
@require_cognito_auth(cognito_validator)
def user_profile_authentication():
    pass

# Register Blueprints
app.register_blueprint(image_controller, url_prefix='/api/images')
app.register_blueprint(model_controller, url_prefix='/api/model')
app.register_blueprint(model_project_controller, url_prefix='/api/model-projects')
app.register_blueprint(story_project_controller, url_prefix='/api/story-projects')
app.register_blueprint(child_profile_controller, url_prefix='/api/child-profiles')
app.register_blueprint(character_controller, url_prefix='/api/characters')
app.register_blueprint(chat_controller, url_prefix='/api/chat')
app.register_blueprint(story_page_controller, url_prefix='/api/story-pages')
app.register_blueprint(config_controller, url_prefix='/api/config')
app.register_blueprint(generation_history_controller, url_prefix='/api/generation-history')
app.register_blueprint(user_profile_controller, url_prefix='/api/user-profile')

# Capture unexpected exceptions and log details to CloudWatch.
@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception(
        "Unhandled exception while processing request",
        extra={
            "path": request.path,
            "method": request.method,
            "user_id": getattr(request, "cognito_user_id", None),
        },
    )
    return jsonify({"error": "Internal server error"}), 500

# # Register Blueprints with auth
# @image_controller.before_request
# def require_auth_for_all():
#     if request.method != 'OPTIONS': # Skip auth for OPTIONS requests
#         require_auth(None)(lambda: None)()  # Runs the auth check for each request
# app.register_blueprint(image_controller, url_prefix='/api/images')

# @model_controller.before_request
# def require_auth_for_all():
#     if request.method != 'OPTIONS': # Skip auth for OPTIONS requests
#         require_auth(None)(lambda: None)()  # Runs the auth check for each request
# app.register_blueprint(model_controller, url_prefix='/api/model')

# @project_controller.before_request
# def require_auth_for_all():
#     if request.method != 'OPTIONS': # Skip auth for OPTIONS requests
#         require_auth(None)(lambda: None)()  # Runs the auth check for each request
# app.register_blueprint(project_controller, url_prefix='/api/projects')

# Define public endpoints
@app.route("/")
def index(): 
    return jsonify({"status": "ok"}), 200

@app.route("/api/health")
def health(): 
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    # Check environment variable to determine the mode
    env = os.getenv("FLASK_ENV", "production")  # Default to production if env is not set
    debug_mode = env == "development"
    port = int(os.getenv("PORT", "5000"))  # Use PORT env var or default to 5000
    app.run(debug=debug_mode, port=port, host='0.0.0.0')
