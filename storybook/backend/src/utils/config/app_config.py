import os
from dotenv import load_dotenv

load_dotenv()


class AppConfig:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    if not S3_BUCKET_NAME:
        raise ValueError("S3_BUCKET_NAME must be defined")

    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    AWS_COGNITO_USER_POOL_ID = os.getenv("AWS_COGNITO_USER_POOL_ID")
    AWS_COGNITO_APP_CLIENT_ID = os.getenv("AWS_COGNITO_APP_CLIENT_ID")

    APP_URL = os.getenv("APP_URL")
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    PORT = int(os.getenv("PORT", "3000"))

    DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_NAME = os.getenv("DATABASE_NAME")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
    REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
