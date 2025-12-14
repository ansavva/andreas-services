from flask import current_app
from src.storage.base import FileStorageAdapter
from src.storage.filesystem import FilesystemStorage
from src.storage.s3 import S3Storage

def get_file_storage() -> FileStorageAdapter:
    """
    Factory function to get the appropriate file storage adapter
    based on the STORAGE_TYPE environment variable.

    Returns:
        FileStorageAdapter: Either FilesystemStorage or S3Storage
    """
    storage_type = current_app.config.get('STORAGE_TYPE', 's3').lower()

    if storage_type == 'filesystem':
        base_path = current_app.config.get('FILE_STORAGE_PATH', './storage')
        return FilesystemStorage(base_path=base_path)
    elif storage_type == 's3':
        bucket_name = current_app.config.get('S3_BUCKET_NAME')
        region = current_app.config.get('AWS_REGION', 'us-east-1')
        return S3Storage(bucket_name=bucket_name, region=region)
    else:
        raise ValueError(f"Unknown storage type: {storage_type}. Must be 'filesystem' or 's3'")
