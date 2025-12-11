import io
import os
from werkzeug.datastructures import FileStorage
from typing import List, Optional
import zipfile

from src.models.file import File
from src.data.project_repo import ProjectRepo
from src.data.image_repo import ImageRepo

class ImageService:
    def __init__(self):
        self.image_repo = ImageRepo()
        self.project_repo = ProjectRepo()

    def upload_file(self, project_id: str, directory: str, file: FileStorage, fileName: str) -> File:
        project = self.project_repo.get_project(project_id)
        return self.image_repo.upload_file(project.key, directory, file, fileName)

    def download_file(self, project_id: str, directory: str, key: str) -> Optional[bytes]:
        project = self.project_repo.get_project(project_id)
        return self.image_repo.download_file(project.key, directory, key)

    def delete_file(self, project_id: str, directory: str, key: str):
        project = self.project_repo.get_project(project_id)
        self.image_repo.delete_file(project.key, directory, key)

    def list_files(self, project_id: str, directory: str) -> List[File]:
        project = self.project_repo.get_project(project_id)
        return self.image_repo.list_files(project.key, directory)
    
    def create_zip(self, project_id: str, directory: str):
        project = self.project_repo.get_project(project_id)
        # List objects in the specified directory
        files = self.list_files(project.id, directory)
        # Create an in-memory zip file
        zip_buffer = io.BytesIO()
        # Create a zip file in memory
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            index = 0
            for file in files:
                # Download each file using the custom download method
                file_blob = self.download_file(project.id, directory, file.key)
                # Rename the file so that the AI knows the subject
                file_extension = os.path.splitext(file.name)[1] 
                fileName = f"a_photo_of_{project.subjectName}({index}){file_extension}"
                # Add the image to the zip file
                zip_file.writestr(fileName, file_blob)
                index = index + 1
        # After adding all files, get the contents of the zip file
        zip_buffer.seek(0)  # Go to the beginning of the buffer before returning it
        return zip_buffer
    
