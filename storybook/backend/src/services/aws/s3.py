import boto3
from datetime import datetime
from typing import List, Optional, Dict

from flask import current_app
from werkzeug.datastructures import FileStorage

from src.utils.config import AppConfig


class S3Storage:
    """S3 storage adapter for production"""

    def __init__(self, bucket_name: str = None, region: Optional[str] = None):
        if bucket_name:
            self.bucket_name = bucket_name
        else:
            self.bucket_name = current_app.config["S3_BUCKET_NAME"]

        self.region = region or AppConfig.AWS_REGION
        self._client = None

    def _get_client(self):
        """Lazy-load S3 client"""
        if self._client is None:
            # Use IAM role credentials (Lambda) or AWS CLI credentials (local)
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def _add_trailing_slash(self, key: str) -> str:
        """Add trailing slash if not present"""
        if not key.endswith("/"):
            key += "/"
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
            return response["Body"].read()
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
            "Bucket": self.bucket_name,
            "Prefix": directory,
        }

        # Add Delimiter if we don't want to include children (subdirectories)
        if not include_children:
            params["Delimiter"] = "/"

        response = client.list_objects_v2(**params)

        if not include_children:
            # Return directory prefixes
            return [
                {
                    "Key": obj["Prefix"],
                    "LastModified": datetime.now(),  # S3 doesn't provide this for prefixes
                }
                for obj in response.get("CommonPrefixes", [])
            ]

        # Retrieve the key and last modified date for each file
        files = [
            {
                "Key": obj["Key"],
                "LastModified": obj["LastModified"],
            }
            for obj in response.get("Contents", [])
        ]

        # Sort files by 'LastModified' in descending order
        files.sort(key=lambda x: x["LastModified"], reverse=True)

        return files

    def create_directory(self, key: str) -> None:
        """Create a directory marker in S3"""
        key = self._add_trailing_slash(key)
        client = self._get_client()
        client.put_object(Bucket=self.bucket_name, Body="", Key=key)

    def generate_presigned_upload(self, key: str, content_type: str, expires_in: int = 3600):
        """Generate a presigned PUT URL for direct browser uploads."""
        client = self._get_client()
        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return {
            "url": url,
            "method": "PUT",
            "headers": {
                "Content-Type": content_type,
            },
        }

    def generate_presigned_download(self, key: str, expires_in: int = 3600):
        """Generate a presigned GET URL for direct browser downloads."""
        client = self._get_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
        return url
