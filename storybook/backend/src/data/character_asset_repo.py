from typing import List, Optional, Dict, Any
from flask import request
import uuid
from datetime import datetime

from src.data.database import get_db
from src.models.character_asset import CharacterAsset

class CharacterAssetRepo:
    """
    CharacterAsset repository - handles CRUD operations for character assets using MongoDB
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_by_id(self, asset_id: str) -> CharacterAsset:
        """
        Get a single character asset by ID for the current user

        Args:
            asset_id: UUID of the character asset

        Returns:
            CharacterAsset object

        Raises:
            ValueError: If asset not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        asset_data = db.character_assets.find_one({
            '_id': asset_id,
            'user_id': user_id
        })

        if not asset_data:
            raise ValueError(f"Character asset with ID {asset_id} not found.")

        return CharacterAsset.from_dict(asset_data)

    def get_by_project(self, project_id: str, asset_type: str = None) -> List[CharacterAsset]:
        """
        Get all character assets for a project, optionally filtered by type

        Args:
            project_id: UUID of the story project
            asset_type: Optional asset type filter

        Returns:
            List of CharacterAsset objects
        """
        db = get_db()
        user_id = self._get_user_id()

        query = {
            'project_id': project_id,
            'user_id': user_id
        }
        if asset_type:
            query['asset_type'] = asset_type

        assets_data = db.character_assets.find(query).sort('created_at', -1)

        return [CharacterAsset.from_dict(a) for a in assets_data]

    def get_approved_portrait(self, project_id: str) -> Optional[CharacterAsset]:
        """
        Get the approved character portrait for a project

        Args:
            project_id: UUID of the story project

        Returns:
            Approved CharacterAsset or None
        """
        db = get_db()
        user_id = self._get_user_id()

        asset_data = db.character_assets.find_one({
            'project_id': project_id,
            'user_id': user_id,
            'asset_type': CharacterAsset.TYPE_PORTRAIT,
            'is_approved': True
        })

        if not asset_data:
            return None

        return CharacterAsset.from_dict(asset_data)

    def get_character_bible(self, project_id: str) -> Optional[CharacterAsset]:
        """
        Get the character bible for a project

        Args:
            project_id: UUID of the story project

        Returns:
            CharacterAsset containing bible data or None
        """
        db = get_db()
        user_id = self._get_user_id()

        asset_data = db.character_assets.find_one({
            'project_id': project_id,
            'user_id': user_id,
            'asset_type': CharacterAsset.TYPE_CHARACTER_BIBLE
        })

        if not asset_data:
            return None

        return CharacterAsset.from_dict(asset_data)

    def create_image_asset(self, project_id: str, asset_type: str, image_id: str,
                          prompt: str = None, scene_name: str = None,
                          stability_image_id: str = None, version: int = 1) -> CharacterAsset:
        """
        Create a new character image asset (portrait or preview scene)

        Args:
            project_id: UUID of the story project
            asset_type: Type of asset (portrait or preview_scene)
            image_id: Reference to Images collection
            prompt: Generation prompt used
            scene_name: Name of the scene (for preview scenes)
            stability_image_id: Stability.ai reference ID
            version: Version number

        Returns:
            Created CharacterAsset object
        """
        if asset_type not in [CharacterAsset.TYPE_PORTRAIT, CharacterAsset.TYPE_PREVIEW_SCENE]:
            raise ValueError(f"Invalid asset type for image: {asset_type}")

        db = get_db()
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.character_assets.insert_one(asset.to_dict())

        return asset

    def create_character_bible(self, project_id: str, bible_data: Dict[str, Any]) -> CharacterAsset:
        """
        Create or update character bible for a project

        Args:
            project_id: UUID of the story project
            bible_data: Dictionary containing character traits, style, reference IDs

        Returns:
            Created/Updated CharacterAsset object
        """
        db = get_db()
        user_id = self._get_user_id()

        # Check if bible already exists
        existing = self.get_character_bible(project_id)
        if existing:
            # Update existing bible
            db.character_assets.update_one(
                {'_id': existing.id, 'user_id': user_id},
                {'$set': {
                    'bible_data': bible_data,
                    'updated_at': datetime.utcnow()
                }}
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.character_assets.insert_one(asset.to_dict())

        return asset

    def approve_asset(self, asset_id: str) -> CharacterAsset:
        """
        Mark an asset as approved

        Args:
            asset_id: UUID of the asset

        Returns:
            Updated CharacterAsset object
        """
        db = get_db()
        user_id = self._get_user_id()

        # First, unapprove all other assets of the same type in the project
        asset = self.get_by_id(asset_id)
        db.character_assets.update_many(
            {
                'project_id': asset.project_id,
                'user_id': user_id,
                'asset_type': asset.asset_type,
                '_id': {'$ne': asset_id}
            },
            {'$set': {'is_approved': False}}
        )

        # Approve this asset
        db.character_assets.update_one(
            {'_id': asset_id, 'user_id': user_id},
            {'$set': {
                'is_approved': True,
                'updated_at': datetime.utcnow()
            }}
        )

        return self.get_by_id(asset_id)

    def delete_asset(self, asset_id: str) -> None:
        """
        Delete a character asset

        Args:
            asset_id: UUID of the asset

        Raises:
            ValueError: If asset not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.character_assets.delete_one({
            '_id': asset_id,
            'user_id': user_id
        })

        if result.deleted_count == 0:
            raise ValueError(f"Character asset with ID {asset_id} not found.")
