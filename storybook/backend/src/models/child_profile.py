from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class ChildProfile:
    """
    ChildProfile model - stores child information for personalized story generation
    Linked to a StoryProject
    """
    id: str  # UUID
    project_id: str  # Reference to StoryProject
    user_id: str  # Cognito user ID (sub claim)
    child_name: str
    child_age: int
    consent_given: bool
    consent_timestamp: Optional[datetime] = None
    photo_ids: Optional[List[str]] = None  # List of image IDs from images collection
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'child_name': self.child_name,
            'child_age': self.child_age,
            'consent_given': self.consent_given,
            'consent_timestamp': self.consent_timestamp,
            'photo_ids': self.photo_ids or [],
            'created_at': self.created_at or datetime.utcnow(),
            'updated_at': self.updated_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'ChildProfile':
        """Create ChildProfile from MongoDB document"""
        return ChildProfile(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            child_name=data.get('child_name'),
            child_age=data.get('child_age'),
            consent_given=data.get('consent_given'),
            consent_timestamp=data.get('consent_timestamp'),
            photo_ids=data.get('photo_ids', []),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
