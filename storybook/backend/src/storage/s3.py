import boto3
from datetime import datetime
from typing import List, Optional, Dict
from werkzeug.datastructures import FileStorage
from flask import current_app

from src.storage.base import FileStorageAdapter

class S3Storage(FileStorageAdapter):
    """S3 storage adapter for production"""

    def __init__(self, bucket_name: str = None, region: str = "us-east-1"):
        if bucket_name:
            self.bucket_name = bucket_name
        else:
            self.bucket_name = current_app.config["S3_BUCKET_NAME"]

        self.region = region
        self._client = None

    def _get_client(self):
        """Lazy-load S3 client"""
        if self._client is None:
            # Use IAM role credentials (Lambda) or AWS CLI credentials (local)
            self._client = boto3.client('s3', region_name=self.region)
        return self._client

    def _add_trailing_slash(self, key: str) -> str:
        """Add trailing slash if not present"""
        if not key.endswith('/'):
            key += '/'
        return key

    def upload_file(self, file: FileStorage, key: str) -> None:
        """Upload a file to S3"""
        client = self._get_client()
        client.upload_fileobj(file, self.bucket_name, key)

    def download_file(self, key: str) -> Optional[bytes]:
        """Download a file from S3"""
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket_name, Key=key)
            return response['Body'].read()
        except client.exceptions.NoSuchKey:
            return None

    def delete_file(self, key: str) -> None:
        """Delete a file from S3"""
        client = self._get_client()
        client.delete_object(Bucket=self.bucket_name, Key=key)

    def list_files(self, directory: str, include_children: bool = True) -> List[Dict]:
        """List files in an S3 directory"""
        if not include_children:
            directory = self._add_trailing_slash(directory)

        client = self._get_client()

        params = {
            'Bucket': self.bucket_name,
            'Prefix': directory
        }

        # Add Delimiter if we don't want to include children (subdirectories)
        if not include_children:
            params['Delimiter'] = '/'

        response = client.list_objects_v2(**params)

        if not include_children:
            # Return directory prefixes
            return [
                {
                    'Key': obj['Prefix'],
                    'LastModified': datetime.now()  # S3 doesn't provide this for prefixes
                }
                for obj in response.get('CommonPrefixes', [])
            ]

        # Retrieve the key and last modified date for each file
        files = [
            {
                'Key': obj['Key'],
                'LastModified': obj['LastModified']
            }
            for obj in response.get('Contents', [])
        ]

        # Sort files by 'LastModified' in descending order
        files.sort(key=lambda x: x['LastModified'], reverse=True)

        return files

    def create_directory(self, key: str) -> None:
        """Create a directory marker in S3"""
        key = self._add_trailing_slash(key)
        client = self._get_client()
        client.put_object(Bucket=self.bucket_name, Body='', Key=key)
