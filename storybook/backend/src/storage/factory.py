from flask import current_app
from src.storage.base import FileStorageAdapter
from src.storage.s3 import S3Storage


def get_file_storage() -> FileStorageAdapter:
    """
    Return the S3 storage adapter for all environments.
    """
    bucket_name = current_app.config.get('S3_BUCKET_NAME')
    if not bucket_name:
        raise ValueError("S3_BUCKET_NAME must be configured")
    region = current_app.config.get('AWS_REGION', 'us-east-1')
    return S3Storage(bucket_name=bucket_name, region=region)
