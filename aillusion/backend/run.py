from dotenv import load_dotenv
import os
from functools import wraps
from flask import Flask, jsonify, request
from authlib.integrations.flask_oauth2 import ResourceProtector
from flask_cors import CORS

from src.config import Config
from src.validator import Auth0JWTBearerTokenValidator
from src.controllers.image_controller import image_controller
from src.controllers.model_controller import model_controller
from src.controllers.project_controller import project_controller

load_dotenv()

# Initialize authentication
require_auth = ResourceProtector()
validator = Auth0JWTBearerTokenValidator(
    os.getenv('AUTH0_DOMAIN'),
    os.getenv('AUTH0_API_ID')
)
require_auth.register_token_validator(validator)

# Initialize Flask app and configuration
app = Flask(__name__)
app.config.from_object(Config)

# Set up CORS
CORS(app, supports_credentials=True)  # Enable CORS for all routes

def require_authentication(func):
    """Decorator to apply authentication check to each request."""
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if request.method != 'OPTIONS':  # Skip auth for OPTIONS requests
            require_auth(None)(lambda: None)()  # Runs the auth check for each request
        return func(*args, **kwargs)
    return decorated_view

# Apply this to your blueprints
@image_controller.before_request
@require_authentication
def image_authentication():
    pass  # No need to repeat the code, just the decorator is enough

@model_controller.before_request
@require_authentication
def model_authentication():
    pass

@project_controller.before_request
@require_authentication
def project_authentication():
    pass

# Register Blueprints
app.register_blueprint(image_controller, url_prefix='/api/images')
app.register_blueprint(model_controller, url_prefix='/api/model')
app.register_blueprint(project_controller, url_prefix='/api/projects')

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
    app.run(debug=debug_mode, port=8080, host='0.0.0.0')
