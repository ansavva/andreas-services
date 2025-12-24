from dotenv import load_dotenv
import os

load_dotenv()  # Load .env file

class Config:
    # Storage configuration
    STORAGE_TYPE = os.getenv("STORAGE_TYPE", "s3")  # 'filesystem' or 's3'
    FILE_STORAGE_PATH = os.getenv("FILE_STORAGE_PATH", "./storage")  # For filesystem storage
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")  # For S3 storage

    # AWS credentials are automatically handled by boto3:
    # - In Lambda: Uses IAM role
    # - Locally: Uses AWS CLI credentials from ~/.aws/credentials
    AWS_REGION = os.getenv("AWS_COGNITO_REGION", "us-east-1")  # Defaults to Cognito region
    AWS_COGNITO_REGION = os.getenv("AWS_COGNITO_REGION", "us-east-1")

    # Database configuration
    # For local dev: mongodb://localhost:27017/storybook_dev
    # For prod: mongodb://username:password@docdb-endpoint:27017/storybook?tls=true&...
    DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017/storybook_dev")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "storybook_dev")

    # AI Service API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")