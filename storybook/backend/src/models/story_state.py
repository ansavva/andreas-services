from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class StoryState:
    """
    StoryState model - stores the structured story data from OpenAI chat
    Represents the evolving story outline, characters, setting, and structure
    Versioned to allow iteration
    """
    id: str  # UUID
    project_id: str  # Reference to StoryProject
    user_id: str  # Cognito user ID (sub claim)
    version: int  # Version number (incremented on each update)

    # Story metadata
    title: Optional[str] = None
    age_range: Optional[str] = None  # e.g., "3-5", "6-8" derived from child age

    # Story structure
    characters: Optional[List[Dict[str, Any]]] = None  # List of character definitions
    setting: Optional[str] = None  # Setting description
    outline: Optional[List[str]] = None  # Story outline as list of plot points
    page_count: Optional[int] = None  # Expected number of pages

    # Additional story elements
    themes: Optional[List[str]] = None  # Story themes
    tone: Optional[str] = None  # Tone/mood of the story

    # Metadata
    is_current: bool = True  # Whether this is the current version
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'version': self.version,
            'title': self.title,
            'age_range': self.age_range,
            'characters': self.characters or [],
            'setting': self.setting,
            'outline': self.outline or [],
            'page_count': self.page_count,
            'themes': self.themes or [],
            'tone': self.tone,
            'is_current': self.is_current,
            'created_at': self.created_at or datetime.utcnow(),
            'updated_at': self.updated_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'StoryState':
        """Create StoryState from MongoDB document"""
        return StoryState(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            version=data.get('version', 1),
            title=data.get('title'),
            age_range=data.get('age_range'),
            characters=data.get('characters', []),
            setting=data.get('setting'),
            outline=data.get('outline', []),
            page_count=data.get('page_count'),
            themes=data.get('themes', []),
            tone=data.get('tone'),
            is_current=data.get('is_current', True),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
