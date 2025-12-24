from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class CharacterAsset:
    """
    CharacterAsset model - stores generated character images and character bible
    Used for character portraits, preview scenes, and character consistency data
    """
    id: str  # UUID
    project_id: str  # Reference to StoryProject
    user_id: str  # Cognito user ID (sub claim)
    asset_type: str  # "portrait", "preview_scene", "character_bible"

    # For images (portrait and preview_scene)
    image_id: Optional[str] = None  # Reference to Images collection
    prompt: Optional[str] = None  # Generation prompt used
    scene_name: Optional[str] = None  # For preview scenes (e.g., "park", "space", "pirate")

    # For character_bible
    bible_data: Optional[Dict[str, Any]] = None  # JSON containing character traits, style, references

    # Generation metadata
    stability_image_id: Optional[str] = None  # Stability.ai image ID for reference
    is_approved: bool = False  # Whether user approved this asset
    version: int = 1  # Version number for regenerations

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Valid asset types
    TYPE_PORTRAIT = "portrait"
    TYPE_PREVIEW_SCENE = "preview_scene"
    TYPE_CHARACTER_BIBLE = "character_bible"

    VALID_TYPES = [TYPE_PORTRAIT, TYPE_PREVIEW_SCENE, TYPE_CHARACTER_BIBLE]

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'asset_type': self.asset_type,
            'image_id': self.image_id,
            'prompt': self.prompt,
            'scene_name': self.scene_name,
            'bible_data': self.bible_data,
            'stability_image_id': self.stability_image_id,
            'is_approved': self.is_approved,
            'version': self.version,
            'created_at': self.created_at or datetime.utcnow(),
            'updated_at': self.updated_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'CharacterAsset':
        """Create CharacterAsset from MongoDB document"""
        return CharacterAsset(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            asset_type=data.get('asset_type'),
            image_id=data.get('image_id'),
            prompt=data.get('prompt'),
            scene_name=data.get('scene_name'),
            bible_data=data.get('bible_data'),
            stability_image_id=data.get('stability_image_id'),
            is_approved=data.get('is_approved', False),
            version=data.get('version', 1),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
