import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
  """Application configuration."""

  mongo_uri: str = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
  mongo_db_name: str = os.getenv('MONGO_DB_NAME', 'HumbuggDb')
  cors_origins: List[str] = field(default_factory=lambda: [
    origin.strip() for origin in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if origin.strip()
  ])
  cors_allow_all: bool = os.getenv('CORS_ALLOW_ALL', 'false').lower() == 'true'
  cognito_user_pool_id: str = os.getenv('COGNITO_USER_POOL_ID', 'us-east-1_example')
  cognito_region: str = os.getenv('COGNITO_REGION', 'us-east-1')
  cognito_client_id: str = os.getenv('COGNITO_CLIENT_ID', 'humbugg-web')
  environ: str = os.getenv('APP_ENV', 'development')
  log_level: str = os.getenv('LOG_LEVEL', 'INFO').upper()
  log_to_cloudwatch: bool = os.getenv('LOG_TO_CLOUDWATCH', 'false').lower() == 'true'
  cloudwatch_log_group: str = os.getenv('CLOUDWATCH_LOG_GROUP', '/humbugg/flask-api')
  log_aws_region: str = os.getenv('LOG_AWS_REGION', os.getenv('COGNITO_REGION', 'us-east-1'))


def load_config() -> Config:
  return Config()
