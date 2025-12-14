import io
import os
from werkzeug.datastructures import FileStorage
from typing import List, Optional
import zipfile

from src.models.image import Image
from src.data.project_repo import ProjectRepo
from src.data.image_repo import ImageRepo

class ImageService:
    def __init__(self):
        self.image_repo = ImageRepo()
        self.project_repo = ProjectRepo()

    def upload_image(self, project_id: str, file: FileStorage, filename: str) -> Image:
        """Upload an image for a project"""
        # Verify project exists and belongs to user
        project = self.project_repo.get_project(project_id)
        return self.image_repo.upload_image(project_id, file, filename)

    def download_image(self, image_id: str) -> Optional[bytes]:
        """Download an image by ID"""
        return self.image_repo.download_image(image_id)

    def delete_image(self, image_id: str):
        """Delete an image by ID"""
        self.image_repo.delete_image(image_id)

    def list_images(self, project_id: str) -> List[Image]:
        """List all images for a project"""
        # Verify project exists and belongs to user
        project = self.project_repo.get_project(project_id)
        return self.image_repo.list_images(project_id)

    def create_zip(self, project_id: str):
        """Create a zip file of all training images for a project"""
        project = self.project_repo.get_project(project_id)
        # List all images for the project
        images = self.list_images(project_id)
        # Create an in-memory zip file
        zip_buffer = io.BytesIO()
        # Create a zip file in memory
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            index = 0
            for image in images:
                # Download each file
                file_blob = self.download_image(image.id)
                # Rename the file so that the AI knows the subject
                file_extension = os.path.splitext(image.filename)[1]
                fileName = f"a_photo_of_{project.subject_name}({index}){file_extension}"
                # Add the image to the zip file
                zip_file.writestr(fileName, file_blob)
                index = index + 1
        # After adding all files, get the contents of the zip file
        zip_buffer.seek(0)  # Go to the beginning of the buffer before returning it
        return zip_buffer
    
