from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()

_BACKEND_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = _BACKEND_DIR / "config"
ASSETS_DIR = _BACKEND_DIR / "assets"

CONFIG_YAML_PATH = CONFIG_DIR / "config.yaml"
if not CONFIG_YAML_PATH.exists():
    raise FileNotFoundError(f"Required config file not found: {CONFIG_YAML_PATH}")

DOCUMENTDB_CA_BUNDLE_PATH = CONFIG_DIR / "global-bundle.pem"


class Config:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    if not S3_BUCKET_NAME:
        raise ValueError("S3_BUCKET_NAME must be defined")

    AWS_COGNITO_REGION = os.getenv("AWS_COGNITO_REGION")
    AWS_COGNITO_USER_POOL_ID = os.getenv("AWS_COGNITO_USER_POOL_ID")
    AWS_COGNITO_APP_CLIENT_ID = os.getenv("AWS_COGNITO_APP_CLIENT_ID")
    AWS_REGION = AWS_COGNITO_REGION

    APP_URL = os.getenv("APP_URL")
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    PORT = int(os.getenv("PORT", "5000"))

    DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_NAME = os.getenv("DATABASE_NAME")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
    REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
