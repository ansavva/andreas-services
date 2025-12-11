from dotenv import load_dotenv
import os
from functools import wraps
from flask import Flask, jsonify, request
from flask_cors import CORS

from src.config import Config
from src.cognito_validator import CognitoJWTValidator, require_cognito_auth
from src.controllers.image_controller import image_controller
from src.controllers.model_controller import model_controller
from src.controllers.project_controller import project_controller

load_dotenv()

# Initialize Cognito authentication
cognito_validator = CognitoJWTValidator(
    region=os.getenv('AWS_COGNITO_REGION', 'us-east-1'),
    user_pool_id=os.getenv('AWS_COGNITO_USER_POOL_ID'),
    app_client_id=os.getenv('AWS_COGNITO_APP_CLIENT_ID')
)

# Initialize Flask app and configuration
app = Flask(__name__)
app.config.from_object(Config)

# Set up CORS
CORS(app, supports_credentials=True)  # Enable CORS for all routes

# Apply Cognito authentication to blueprints
@image_controller.before_request
@require_cognito_auth(cognito_validator)
def image_authentication():
    pass

@model_controller.before_request
@require_cognito_auth(cognito_validator)
def model_authentication():
    pass

@project_controller.before_request
@require_cognito_auth(cognito_validator)
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
