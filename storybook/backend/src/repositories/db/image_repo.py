import os
from flask import request
from werkzeug.datastructures import FileStorage
from typing import List, Optional
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.image import Image
from src.services.aws.s3 import S3Storage


class ImageRepo:
    """
    Image repository - handles image metadata in DynamoDB and files in S3.
    Table: STORYBOOK_IMAGES_TABLE  PK: image_id (S)
    GSI: project_id-created_at-index  PK: project_id (S), SK: created_at (S)
    """

    def __init__(self):
        self._storage = None

    @property
    def storage(self):
        """Lazy-load storage adapter to avoid app context issues"""
        if self._storage is None:
            self._storage = S3Storage()
        return self._storage

    def get_current_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims["sub"]

    def _get_user_id(self) -> str:
        """Backward-compatible alias for getting user id."""
        return self.get_current_user_id()

    @staticmethod
    def _table():
        return _table('STORYBOOK_IMAGES_TABLE')

    def _create_s3_key(self, project_id: str, image_id: str, filename: str) -> str:
        """Generate S3 key for image storage"""
        user_id = self._get_user_id()
        project_id_str = str(project_id)
        return f"users/{user_id}/projects/{project_id_str}/images/{image_id}_{filename}"

    def build_s3_key(self, project_id: str, image_id: str, filename: str) -> str:
        """Public helper to generate S3 key for image storage"""
        return self._create_s3_key(project_id, image_id, filename)

    def upload_image(
        self,
        project_id: str,
        file: FileStorage,
        filename: str,
        image_type: str = "training",
        image_id: Optional[str] = None,
        processing: bool = False,
    ) -> Image:
        """Upload an image file to S3 and save metadata to DynamoDB."""
        user_id = self._get_user_id()
        project_id = str(project_id)
        image_id = image_id or str(uuid.uuid4())
        s3_key = self._create_s3_key(project_id, image_id, filename)

        self.storage.upload_file(file, s3_key)

        image = Image(
            id=image_id,
            project_id=project_id,
            user_id=user_id,
            s3_key=s3_key,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=file.content_length or 0,
            image_type=image_type,
            processing=processing,
            created_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=image.to_dict())
        return image

    def create_image_record(
        self,
        project_id: str,
        image_id: str,
        filename: str,
        s3_key: str,
        content_type: str,
        size_bytes: int,
        image_type: str = "training",
        processing: bool = False,
    ) -> Image:
        """Create an image metadata record without uploading the file."""
        user_id = self._get_user_id()

        image = Image(
            id=image_id,
            project_id=str(project_id),
            user_id=user_id,
            s3_key=s3_key,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            size_bytes=size_bytes,
            image_type=image_type,
            processing=processing,
            created_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=image.to_dict())
        return image

    def get_image(self, image_id: str) -> Image:
        """
        Get image metadata by ID for the current user.

        Raises:
            ValueError: If image not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'image_id': image_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Image with ID {image_id} not found.")

        return Image.from_dict(item)

    def get_image_any_user(self, image_id: str) -> Image:
        """Fetch image metadata by ID without enforcing user ownership."""
        resp = self._table().get_item(Key={'image_id': image_id})
        item = resp.get('Item')
        if not item:
            raise ValueError(f"Image with ID {image_id} not found.")
        return Image.from_dict(item)

    def list_images(self, project_id: str, image_type: Optional[str] = None) -> List[Image]:
        """
        List all images for a project, optionally filtered by image type.
        Results are sorted by created_at descending (most recent first).
        """
        user_id = self._get_user_id()
        project_id = str(project_id)

        filter_expr = Attr('user_id').eq(user_id)
        if image_type:
            filter_expr = filter_expr & Attr('image_type').eq(image_type)

        resp = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=filter_expr,
            ScanIndexForward=False,
        )

        return [Image.from_dict(img) for img in resp.get('Items', [])]

    def list_images_excluding_ids(
        self,
        project_id: str,
        exclude_ids: List[str],
        image_type: Optional[str] = None,
    ) -> List[Image]:
        """List images for a project, excluding specific image IDs."""
        images = self.list_images(project_id, image_type=image_type)
        if not exclude_ids:
            return images
        exclude_set = set(exclude_ids)
        return [img for img in images if img.id not in exclude_set]

    def get_images_by_ids(self, image_ids: List[str]) -> List[Image]:
        """Fetch specific images for the current user by ID."""
        if not image_ids:
            return []

        user_id = self._get_user_id()
        result = []
        for image_id in image_ids:
            resp = self._table().get_item(Key={'image_id': image_id})
            item = resp.get('Item')
            if item and item.get('user_id') == user_id:
                result.append(Image.from_dict(item))
        return result

    def download_image(self, image_id: str) -> Optional[bytes]:
        """Download image file from S3."""
        image = self.get_image(image_id)
        return self.storage.download_file(image.s3_key)

    def delete_image(self, image_id: str) -> None:
        """
        Delete image metadata from DynamoDB and file from S3.

        Raises:
            ValueError: If image not found or doesn't belong to user
        """
        image = self.get_image(image_id)

        if image.s3_key:
            self.storage.delete_file(image.s3_key)

        self._table().delete_item(Key={'image_id': image_id})

    def delete_project_images(self, project_id: str) -> None:
        """Delete all images for a project (called when deleting a project)."""
        images = self.list_images(project_id)

        for image in images:
            self.storage.delete_file(image.s3_key)

        table = self._table()
        with table.batch_writer() as batch:
            for image in images:
                batch.delete_item(Key={'image_id': image.id})
