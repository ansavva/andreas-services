from dotenv import load_dotenv
import os

load_dotenv()  # Load .env file

class Config:
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    # AWS credentials are automatically handled by boto3:
    # - In Lambda: Uses IAM role
    # - Locally: Uses AWS CLI credentials from ~/.aws/credentials
    AWS_REGION = os.getenv("AWS_COGNITO_REGION", "us-east-1")  # Defaults to Cognito region
    AWS_COGNITO_REGION = os.getenv("AWS_COGNITO_REGION", "us-east-1")