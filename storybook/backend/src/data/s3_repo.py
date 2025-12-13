import boto3
from flask import current_app
from werkzeug.datastructures import FileStorage
from typing import Optional

class S3Repo:
    def __get_s3_client(self):
        config = current_app.config
        # Use IAM role credentials (Lambda) or AWS CLI credentials (local)
        # No need to pass access keys explicitly
        return boto3.client(
            's3',
            region_name=config.get("AWS_REGION", "us-east-1")
        )
    
    def __get_bucket_name(self):
        config = current_app.config
        return config["S3_BUCKET_NAME"]
    
    def __add_trailing_slash(self, key: str) -> str:
        # Check if the string ends with a '/' and add it if not
        if not key.endswith('/'):
            key += '/'
        return key

    def upload_file(self, file: FileStorage, key: str):
        s3_client = self.__get_s3_client()
        bucket_name = self.__get_bucket_name()
        s3_client.upload_fileobj(file, bucket_name, key)

    def create_directory(self, key: str):
        key = self.__add_trailing_slash(key)
        s3_client = self.__get_s3_client()
        bucket_name = self.__get_bucket_name()
        s3_client.put_object(Bucket=bucket_name, Body='', Key=key)

    def download_file(self, key: str) -> Optional[bytes]:
        s3_client = self.__get_s3_client()
        bucket_name = self.__get_bucket_name()
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        return response['Body'].read()

    def delete_file(self, key: str):
        s3_client = self.__get_s3_client()
        bucket_name = self.__get_bucket_name()
        s3_client.delete_object(Bucket=bucket_name, Key=key)

    def list_files(self, directory: str, include_children: bool = True):
        if not include_children:
            directory = self.__add_trailing_slash(directory)

        s3_client = self.__get_s3_client()
        bucket_name = self.__get_bucket_name()

        # Use a delimiter to avoid child items if include_children is False
        params = {
            'Bucket': bucket_name,
            'Prefix': directory
        }

        # Add Delimiter if we don't want to include children (subdirectories)
        if not include_children:
            params['Delimiter'] = '/'

        response = s3_client.list_objects_v2(**params)

        if not include_children: 
            return [obj['Prefix'] for obj in response.get('CommonPrefixes', [])]
        
         # Retrieve the key and last modified date for each file
        files = [
            {
                'Key': obj['Key'],
                'LastModified': obj['LastModified']
            }
            for obj in response.get('Contents', [])
        ]

        # Sort files by 'LastModified' in descending order
        sorted_files = sorted(files, key=lambda x: x['LastModified'], reverse=True)

        # Return just the keys, sorted by modification date
        return [file['Key'] for file in sorted_files]

