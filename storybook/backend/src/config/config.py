from dotenv import load_dotenv
import os
from pathlib import Path
import logging

load_dotenv()  # Load .env file

logger = logging.getLogger(__name__)

# Project paths - single source of truth for file locations
_BACKEND_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = _BACKEND_DIR / "config"
ASSETS_DIR = _BACKEND_DIR / "assets"

# Specific file paths - fail fast if they don't exist
CONFIG_YAML_PATH = CONFIG_DIR / "config.yaml"
if not CONFIG_YAML_PATH.exists():
    raise FileNotFoundError(f"Required config file not found: {CONFIG_YAML_PATH}")

# DocumentDB CA bundle - only required for production (not for local MongoDB)
DOCUMENTDB_CA_BUNDLE_PATH = CONFIG_DIR / "global-bundle.pem"

def _get_required_env(key: str) -> str:
    """Get required environment variable or raise error"""
    value = os.getenv(key)
    if not value:
        error_msg = f"Required environment variable not set: {key}"
        # Print to stdout/stderr for CloudWatch before logging is configured
        print(f"ERROR: Missing required environment variable: {key}", flush=True)
        logger.error("Missing required environment variable", extra={"variable_name": key})
        raise ValueError(error_msg)
    return value

class Config:
    # Logging configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # Optional, defaults to INFO

    # Storage configuration
    STORAGE_TYPE = _get_required_env("STORAGE_TYPE")
    FILE_STORAGE_PATH = os.getenv("FILE_STORAGE_PATH")  # Optional, only for filesystem storage
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")  # Optional, only for S3 storage

    # AWS Cognito configuration
    AWS_COGNITO_REGION = _get_required_env("AWS_COGNITO_REGION")
    AWS_COGNITO_USER_POOL_ID = _get_required_env("AWS_COGNITO_USER_POOL_ID")
    AWS_COGNITO_APP_CLIENT_ID = _get_required_env("AWS_COGNITO_APP_CLIENT_ID")
    AWS_REGION = AWS_COGNITO_REGION  # Use same region for all AWS services

    # Application configuration
    APP_URL = _get_required_env("APP_URL")
    FLASK_ENV = os.getenv("FLASK_ENV", "production")  # Optional, defaults to production
    PORT = int(os.getenv("PORT", "5000"))  # Optional, defaults to 5000

    # Database configuration
    DATABASE_URL = _get_required_env("DATABASE_URL")
    DATABASE_NAME = _get_required_env("DATABASE_NAME")

    # AI Service API Keys - all required
    OPENAI_API_KEY = _get_required_env("OPENAI_API_KEY")
    STABILITY_API_KEY = _get_required_env("STABILITY_API_KEY")
    REPLICATE_API_TOKEN = _get_required_env("REPLICATE_API_TOKEN")
