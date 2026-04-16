from typing import List, Optional, Dict, Any
from flask import request
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.character_asset import CharacterAsset


class CharacterAssetRepo:
    """
    CharacterAsset repository - handles CRUD operations for character assets using DynamoDB.
    Table: STORYBOOK_CHARACTER_ASSETS_TABLE  PK: asset_id (S)
    GSI: project_id-created_at-index  PK: project_id (S), SK: created_at (S)
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_CHARACTER_ASSETS_TABLE')

    def get_by_id(self, asset_id: str) -> CharacterAsset:
        """
        Get a single character asset by ID for the current user.

        Raises:
            ValueError: If asset not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'asset_id': asset_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Character asset with ID {asset_id} not found.")

        return CharacterAsset.from_dict(item)

    def get_by_project(self, project_id: str, asset_type: str = None) -> List[CharacterAsset]:
        """
        Get all character assets for a project, optionally filtered by type.
        Results are sorted by created_at descending.
        """
        user_id = self._get_user_id()

        filter_expr = Attr('user_id').eq(user_id)
        if asset_type:
            filter_expr = filter_expr & Attr('asset_type').eq(asset_type)

        resp = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=filter_expr,
            ScanIndexForward=False,  # descending by created_at
        )

        return [CharacterAsset.from_dict(a) for a in resp.get('Items', [])]

    def get_approved_portrait(self, project_id: str) -> Optional[CharacterAsset]:
        """Get the approved character portrait for a project."""
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=(
                Attr('user_id').eq(user_id) &
                Attr('asset_type').eq(CharacterAsset.TYPE_PORTRAIT) &
                Attr('is_approved').eq(True)
            ),
            ScanIndexForward=False,
        )

        items = resp.get('Items', [])
        if not items:
            return None

        return CharacterAsset.from_dict(items[0])

    def get_character_bible(self, project_id: str) -> Optional[CharacterAsset]:
        """Get the character bible for a project."""
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=(
                Attr('user_id').eq(user_id) &
                Attr('asset_type').eq(CharacterAsset.TYPE_CHARACTER_BIBLE)
            ),
            ScanIndexForward=False,
        )

        items = resp.get('Items', [])
        if not items:
            return None

        return CharacterAsset.from_dict(items[0])

    def create_image_asset(self, project_id: str, asset_type: str, image_id: str,
                           prompt: str = None, scene_name: str = None,
                           stability_image_id: str = None, version: int = 1) -> CharacterAsset:
        """Create a new character image asset (portrait or preview scene)."""
        if asset_type not in [CharacterAsset.TYPE_PORTRAIT, CharacterAsset.TYPE_PREVIEW_SCENE]:
            raise ValueError(f"Invalid asset type for image: {asset_type}")

        user_id = self._get_user_id()
        asset_id = str(uuid.uuid4())
        asset = CharacterAsset(
            id=asset_id,
            project_id=project_id,
            user_id=user_id,
            asset_type=asset_type,
            image_id=image_id,
            prompt=prompt,
            scene_name=scene_name,
            stability_image_id=stability_image_id,
            version=version,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=asset.to_dict())
        return asset

    def create_character_bible(self, project_id: str, bible_data: Dict[str, Any]) -> CharacterAsset:
        """Create or update character bible for a project."""
        user_id = self._get_user_id()

        # Check if bible already exists
        existing = self.get_character_bible(project_id)
        if existing:
            now = datetime.now(timezone.utc).isoformat()
            self._table().update_item(
                Key={'asset_id': existing.id},
                UpdateExpression='SET bible_data = :bible_data, updated_at = :updated_at',
                ExpressionAttributeValues={
                    ':bible_data': bible_data,
                    ':updated_at': now,
                },
            )
            return self.get_by_id(existing.id)

        # Create new bible
        asset_id = str(uuid.uuid4())
        asset = CharacterAsset(
            id=asset_id,
            project_id=project_id,
            user_id=user_id,
            asset_type=CharacterAsset.TYPE_CHARACTER_BIBLE,
            bible_data=bible_data,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=asset.to_dict())
        return asset

    def approve_asset(self, asset_id: str) -> CharacterAsset:
        """
        Mark an asset as approved.
        First unapproves all other assets of the same type in the project (read-modify-write).
        """
        asset = self.get_by_id(asset_id)
        user_id = self._get_user_id()
        now = datetime.now(timezone.utc).isoformat()

        # Unapprove all other assets of the same type in the project
        others = self.get_by_project(asset.project_id, asset_type=asset.asset_type)
        table = self._table()
        for other in others:
            if other.id != asset_id and getattr(other, 'is_approved', False):
                table.update_item(
                    Key={'asset_id': other.id},
                    UpdateExpression='SET is_approved = :false',
                    ExpressionAttributeValues={':false': False},
                )

        # Approve this asset
        table.update_item(
            Key={'asset_id': asset_id},
            UpdateExpression='SET is_approved = :true, updated_at = :updated_at',
            ExpressionAttributeValues={':true': True, ':updated_at': now},
        )

        return self.get_by_id(asset_id)

    def delete_asset(self, asset_id: str) -> None:
        """
        Delete a character asset.

        Raises:
            ValueError: If asset not found or doesn't belong to user
        """
        # Validates ownership
        self.get_by_id(asset_id)
        self._table().delete_item(Key={'asset_id': asset_id})
