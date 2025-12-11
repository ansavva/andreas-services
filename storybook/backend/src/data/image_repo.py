import os
from authlib.integrations.flask_oauth2 import current_token
from werkzeug.datastructures import FileStorage
from typing import List, Optional
import uuid

from src.models.file import File
from src.data.s3_repo import S3Repo

class ImageRepo:
    def __init__(self):
        self.s3_repo = S3Repo()
    
    def __create_directory(self, project_key: str, directory: str):
        user_id = current_token.sub.split('|')[1]
        return f"users/{user_id}/projects/{project_key}/{directory}"

    def upload_file(self, project_key: str, directory: str, file: FileStorage, fileName: str) -> File:
        file_guid = str(uuid.uuid4())
        user_directory = self.__create_directory(project_key, directory)
        key = f"{user_directory}/{file_guid}__ai__{fileName}"
        self.s3_repo.upload_file(file, key)
        return File(id=file_guid, name=fileName, key=f"{file_guid}__ai__{fileName}")

    def download_file(self, project_key: str, directory: str, key: str) -> Optional[bytes]:
        user_directory = self.__create_directory(project_key, directory)
        return self.s3_repo.download_file(f"{user_directory}/{key}")

    def delete_file(self, project_key: str, directory: str, key: str):
        user_directory = self.__create_directory(project_key, directory)
        self.s3_repo.delete_file(f"{user_directory}/{key}")

    def list_files(self, project_key: str, directory: str) -> List[File]:
        # Get all files from s3
        user_directory = self.__create_directory(project_key, directory)
        files = self.s3_repo.list_files(user_directory)
        # Get only the file name (remove directory)
        file_names = [os.path.basename(file_path) for file_path in files]
        # Create file models
        file_models = []
        for file_name in file_names:
            # Split by the delimiter __ai__
            parts = file_name.split("__ai__")
            # Ensure we have exactly 2 parts, otherwise handle the error
            if len(parts) == 2:
                file_id, file_name_part = parts
                file_models.append(File(id=file_id, name=file_name_part, key=file_name))
        return file_models
    
