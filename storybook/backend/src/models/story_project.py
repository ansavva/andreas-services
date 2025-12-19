from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class StoryProject:
    """
    StoryProject model - represents a complete storybook project
    Extends the basic Project model with story-specific fields

    State machine:
    DRAFT_SETUP -> CHARACTER_PREVIEW -> CHAT -> COMPILED -> ILLUSTRATING -> READY -> EXPORTED
    """
    id: str  # UUID
    name: str
    user_id: str  # Cognito user ID (sub claim)

    # Story-specific fields
    status: str  # State machine status
    child_profile_id: Optional[str] = None  # Reference to ChildProfile
    character_bible_id: Optional[str] = None  # Reference to character bible (stored as CharacterAsset)
    story_state_id: Optional[str] = None  # Reference to current StoryState

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Valid status values
    STATUS_DRAFT_SETUP = "DRAFT_SETUP"
    STATUS_CHARACTER_PREVIEW = "CHARACTER_PREVIEW"
    STATUS_CHAT = "CHAT"
    STATUS_COMPILED = "COMPILED"
    STATUS_ILLUSTRATING = "ILLUSTRATING"
    STATUS_READY = "READY"
    STATUS_EXPORTED = "EXPORTED"

    VALID_STATUSES = [
        STATUS_DRAFT_SETUP,
        STATUS_CHARACTER_PREVIEW,
        STATUS_CHAT,
        STATUS_COMPILED,
        STATUS_ILLUSTRATING,
        STATUS_READY,
        STATUS_EXPORTED
    ]

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'name': self.name,
            'user_id': self.user_id,
            'status': self.status,
            'child_profile_id': self.child_profile_id,
            'character_bible_id': self.character_bible_id,
            'story_state_id': self.story_state_id,
            'created_at': self.created_at or datetime.utcnow(),
            'updated_at': self.updated_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'StoryProject':
        """Create StoryProject from MongoDB document"""
        return StoryProject(
            id=str(data.get('_id')),
            name=data.get('name'),
            user_id=data.get('user_id'),
            status=data.get('status'),
            child_profile_id=data.get('child_profile_id'),
            character_bible_id=data.get('character_bible_id'),
            story_state_id=data.get('story_state_id'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
