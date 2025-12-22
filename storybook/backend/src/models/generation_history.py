from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class GenerationHistory:
    """
    Generation History model - represents a prompt + generated images entry
    Immutable history of image generation for a project
    """
    id: str  # UUID or MongoDB _id
    project_id: str  # Reference to Project
    user_id: str  # Cognito user ID (sub claim) - the creator
    prompt: str  # The exact prompt submitted
    image_ids: List[str]  # List of Image IDs generated from this prompt
    created_at: Optional[datetime] = None
    reference_image_ids: Optional[List[str]] = None  # Reference images used for this generation

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        data = {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'prompt': self.prompt,
            'image_ids': self.image_ids,
            'created_at': self.created_at or datetime.utcnow()
        }
        if self.reference_image_ids is not None:
            data['reference_image_ids'] = self.reference_image_ids
        return data

    @staticmethod
    def from_dict(data: dict) -> 'GenerationHistory':
        """Create GenerationHistory from MongoDB document"""
        return GenerationHistory(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            prompt=data.get('prompt'),
            image_ids=data.get('image_ids', []),
            created_at=data.get('created_at'),
            reference_image_ids=data.get('reference_image_ids')
        )
