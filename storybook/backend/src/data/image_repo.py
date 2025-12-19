import os
from flask import request
from werkzeug.datastructures import FileStorage
from typing import List, Optional
import uuid
from datetime import datetime

from src.data.database import get_db
from src.models.image import Image
from src.storage.factory import get_file_storage

class ImageRepo:
    """
    Image repository - handles image metadata in MongoDB and files in S3
    """

    def __init__(self):
        self._storage = None

    @property
    def storage(self):
        """Lazy-load storage adapter to avoid app context issues"""
        if self._storage is None:
            self._storage = get_file_storage()
        return self._storage

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def _create_s3_key(self, project_id: str, image_id: str, filename: str) -> str:
        """Generate S3 key for image storage"""
        user_id = self._get_user_id()
        # Ensure project_id is a string (could be ObjectId from MongoDB)
        project_id_str = str(project_id)
        return f"users/{user_id}/projects/{project_id_str}/images/{image_id}_{filename}"

    def upload_image(self, project_id: str, file: FileStorage, filename: str) -> Image:
        """
        Upload an image file to S3 and save metadata to MongoDB

        Args:
            project_id: UUID of the project this image belongs to
            file: File upload from request
            filename: Original filename

        Returns:
            Created Image object
        """
        db = get_db()
        user_id = self._get_user_id()

        # Ensure project_id is a string (could be ObjectId from MongoDB)
        project_id = str(project_id)

        image_id = str(uuid.uuid4())
        s3_key = self._create_s3_key(project_id, image_id, filename)

        # Upload file to S3
        self.storage.upload_file(file, s3_key)

        # Save metadata to MongoDB
        image = Image(
            id=image_id,
            project_id=project_id,
            user_id=user_id,
            s3_key=s3_key,
            filename=filename,
            content_type=file.content_type or 'application/octet-stream',
            size_bytes=file.content_length or 0,
            created_at=datetime.utcnow()
        )

        db.images.insert_one(image.to_dict())

        return image

    def get_image(self, image_id: str) -> Image:
        """
        Get image metadata by ID

        Args:
            image_id: UUID of the image

        Returns:
            Image object

        Raises:
            ValueError: If image not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        image_data = db.images.find_one({
            '_id': image_id,
            'user_id': user_id
        })

        if not image_data:
            raise ValueError(f"Image with ID {image_id} not found.")

        return Image.from_dict(image_data)

    def list_images(self, project_id: str) -> List[Image]:
        """
        List all images for a project

        Args:
            project_id: UUID of the project

        Returns:
            List of Image objects
        """
        db = get_db()
        user_id = self._get_user_id()

        # Ensure project_id is a string (could be ObjectId from MongoDB)
        project_id = str(project_id)

        images_data = db.images.find({
            'project_id': project_id,
            'user_id': user_id
        }).sort('created_at', -1)  # Most recent first

        return [Image.from_dict(img) for img in images_data]

    def download_image(self, image_id: str) -> Optional[bytes]:
        """
        Download image file from S3

        Args:
            image_id: UUID of the image

        Returns:
            Image file bytes

        Raises:
            ValueError: If image not found or doesn't belong to user
        """
        image = self.get_image(image_id)
        return self.storage.download_file(image.s3_key)

    def delete_image(self, image_id: str) -> None:
        """
        Delete image metadata from MongoDB and file from S3

        Args:
            image_id: UUID of the image

        Raises:
            ValueError: If image not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        # First, get the image to get S3 key
        image = self.get_image(image_id)

        # Delete from S3
        self.storage.delete_file(image.s3_key)

        # Delete metadata from MongoDB
        result = db.images.delete_one({
            '_id': image_id,
            'user_id': user_id
        })

        if result.deleted_count == 0:
            raise ValueError(f"Image with ID {image_id} not found.")

    def delete_project_images(self, project_id: str) -> None:
        """
        Delete all images for a project (called when deleting a project)

        Args:
            project_id: UUID of the project
        """
        db = get_db()
        user_id = self._get_user_id()

        # Get all images for the project
        images = self.list_images(project_id)

        # Delete all files from S3
        for image in images:
            self.storage.delete_file(image.s3_key)

        # Delete all metadata from MongoDB
        db.images.delete_many({
            'project_id': project_id,
            'user_id': user_id
        })
