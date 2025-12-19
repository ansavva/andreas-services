from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class StoryPage:
    """
    StoryPage model - represents a single page in the storybook
    Contains page text and illustration information
    Supports versioning for text and image regeneration
    """
    id: str  # UUID
    project_id: str  # Reference to StoryProject
    user_id: str  # Cognito user ID (sub claim)
    page_number: int  # Page number in the story (1-indexed)

    # Page content
    page_text: str  # The story text for this page
    text_version: int = 1  # Version of the text

    # Illustration metadata
    illustration_prompt: Optional[str] = None  # Base prompt for image generation
    scene_description: Optional[str] = None  # Scene description
    must_include: Optional[List[str]] = None  # Elements that must be included
    must_avoid: Optional[List[str]] = None  # Elements to avoid

    # Generated image
    image_s3_key: Optional[str] = None  # S3 path to current illustration
    image_url: Optional[str] = None  # Public/signed URL if needed
    stability_image_id: Optional[str] = None  # Stability.ai image ID
    image_version: int = 1  # Version of the illustration

    # Image variants (for selection)
    variant_s3_keys: Optional[List[str]] = None  # S3 paths to alternative images

    # Status
    is_compiled: bool = False  # Whether text is finalized from compilation
    has_illustration: bool = False  # Whether illustration has been generated

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'page_number': self.page_number,
            'page_text': self.page_text,
            'text_version': self.text_version,
            'illustration_prompt': self.illustration_prompt,
            'scene_description': self.scene_description,
            'must_include': self.must_include or [],
            'must_avoid': self.must_avoid or [],
            'image_s3_key': self.image_s3_key,
            'image_url': self.image_url,
            'stability_image_id': self.stability_image_id,
            'image_version': self.image_version,
            'variant_s3_keys': self.variant_s3_keys or [],
            'is_compiled': self.is_compiled,
            'has_illustration': self.has_illustration,
            'created_at': self.created_at or datetime.utcnow(),
            'updated_at': self.updated_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'StoryPage':
        """Create StoryPage from MongoDB document"""
        return StoryPage(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            page_number=data.get('page_number'),
            page_text=data.get('page_text'),
            text_version=data.get('text_version', 1),
            illustration_prompt=data.get('illustration_prompt'),
            scene_description=data.get('scene_description'),
            must_include=data.get('must_include', []),
            must_avoid=data.get('must_avoid', []),
            image_s3_key=data.get('image_s3_key'),
            image_url=data.get('image_url'),
            stability_image_id=data.get('stability_image_id'),
            image_version=data.get('image_version', 1),
            variant_s3_keys=data.get('variant_s3_keys', []),
            is_compiled=data.get('is_compiled', False),
            has_illustration=data.get('has_illustration', False),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
