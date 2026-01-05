from typing import List, Optional, Dict, Any
from flask import request
import uuid
from datetime import datetime

from src.repositories.db.database import get_db
from src.models.story_state import StoryState

class StoryStateRepo:
    """
    StoryState repository - handles CRUD operations for story states using MongoDB
    Supports versioning for iterative story development
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_by_id(self, state_id: str) -> StoryState:
        """
        Get a single story state by ID for the current user

        Args:
            state_id: UUID of the story state

        Returns:
            StoryState object

        Raises:
            ValueError: If state not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        state_data = db.story_states.find_one({
            '_id': state_id,
            'user_id': user_id
        })

        if not state_data:
            raise ValueError(f"Story state with ID {state_id} not found.")

        return StoryState.from_dict(state_data)

    def get_current(self, project_id: str) -> Optional[StoryState]:
        """
        Get the current (latest) story state for a project

        Args:
            project_id: UUID of the story project

        Returns:
            Current StoryState object or None if no state exists
        """
        db = get_db()
        user_id = self._get_user_id()

        state_data = db.story_states.find_one({
            'project_id': project_id,
            'user_id': user_id,
            'is_current': True
        })

        if not state_data:
            return None

        return StoryState.from_dict(state_data)

    def get_all_versions(self, project_id: str) -> List[StoryState]:
        """
        Get all versions of story state for a project

        Args:
            project_id: UUID of the story project

        Returns:
            List of StoryState objects sorted by version (newest first)
        """
        db = get_db()
        user_id = self._get_user_id()

        states_data = db.story_states.find({
            'project_id': project_id,
            'user_id': user_id
        }).sort('version', -1)

        return [StoryState.from_dict(s) for s in states_data]

    def create_or_update(self, project_id: str, title: str = None,
                        age_range: str = None, characters: List[Dict[str, Any]] = None,
                        setting: str = None, outline: List[str] = None,
                        page_count: int = None, themes: List[str] = None,
                        tone: str = None) -> StoryState:
        """
        Create a new story state version or update the current one

        Args:
            project_id: UUID of the story project
            title: Story title
            age_range: Target age range
            characters: List of character definitions
            setting: Setting description
            outline: Story outline
            page_count: Number of pages
            themes: Story themes
            tone: Story tone

        Returns:
            Created/Updated StoryState object
        """
        db = get_db()
        user_id = self._get_user_id()

        # Get current version number
        current = self.get_current(project_id)
        next_version = 1 if not current else current.version + 1

        # Mark all previous versions as not current
        db.story_states.update_many(
            {
                'project_id': project_id,
                'user_id': user_id
            },
            {'$set': {'is_current': False}}
        )

        # Create new version
        state_id = str(uuid.uuid4())
        state = StoryState(
            id=state_id,
            project_id=project_id,
            user_id=user_id,
            version=next_version,
            title=title,
            age_range=age_range,
            characters=characters,
            setting=setting,
            outline=outline,
            page_count=page_count,
            themes=themes,
            tone=tone,
            is_current=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.story_states.insert_one(state.to_dict())

        return state

    def update_fields(self, state_id: str, **kwargs) -> StoryState:
        """
        Update specific fields of the current story state

        Args:
            state_id: UUID of the story state
            **kwargs: Fields to update

        Returns:
            Updated StoryState object
        """
        db = get_db()
        user_id = self._get_user_id()

        update_fields = {'updated_at': datetime.utcnow()}
        allowed_fields = ['title', 'age_range', 'characters', 'setting',
                         'outline', 'page_count', 'themes', 'tone']

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                update_fields[key] = value

        result = db.story_states.update_one(
            {'_id': state_id, 'user_id': user_id, 'is_current': True},
            {'$set': update_fields}
        )

        if result.matched_count == 0:
            raise ValueError(f"Story state with ID {state_id} not found or not current.")

        return self.get_by_id(state_id)

    def revert_to_version(self, project_id: str, version: int) -> StoryState:
        """
        Revert to a previous version (makes it current)

        Args:
            project_id: UUID of the story project
            version: Version number to revert to

        Returns:
            The reverted StoryState (now marked as current)
        """
        db = get_db()
        user_id = self._get_user_id()

        # Find the version to revert to
        state_data = db.story_states.find_one({
            'project_id': project_id,
            'user_id': user_id,
            'version': version
        })

        if not state_data:
            raise ValueError(f"Story state version {version} not found.")

        # Mark all versions as not current
        db.story_states.update_many(
            {'project_id': project_id, 'user_id': user_id},
            {'$set': {'is_current': False}}
        )

        # Mark this version as current
        db.story_states.update_one(
            {'_id': str(state_data['_id']), 'user_id': user_id},
            {'$set': {'is_current': True, 'updated_at': datetime.utcnow()}}
        )

        return self.get_by_id(str(state_data['_id']))

    def delete_all_for_project(self, project_id: str) -> None:
        """
        Delete all story states for a project

        Args:
            project_id: UUID of the story project
        """
        db = get_db()
        user_id = self._get_user_id()

        db.story_states.delete_many({
            'project_id': project_id,
            'user_id': user_id
        })
