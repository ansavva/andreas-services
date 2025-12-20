from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class UserProfile:
    """
    UserProfile model - stores user profile information
    One profile per Cognito user (sub)
    """
    user_id: str  # Cognito user ID (sub claim) - also serves as _id in MongoDB
    display_name: Optional[str] = None  # User's chosen display name
    profile_image_id: Optional[str] = None  # Reference to Image in images collection
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.user_id,  # Use user_id as the primary key
            'display_name': self.display_name,
            'profile_image_id': self.profile_image_id,
            'created_at': self.created_at or datetime.utcnow(),
            'updated_at': self.updated_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'UserProfile':
        """Create UserProfile from MongoDB document"""
        return UserProfile(
            user_id=str(data.get('_id')),
            display_name=data.get('display_name'),
            profile_image_id=data.get('profile_image_id'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
