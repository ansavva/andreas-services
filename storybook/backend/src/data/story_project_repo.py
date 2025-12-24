from typing import List, Optional
from flask import request
import uuid
from datetime import datetime

from src.data.database import get_db
from src.models.story_project import StoryProject

class StoryProjectRepo:
    """
    StoryProject repository - handles CRUD operations for story projects using MongoDB
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_project(self, project_id: str) -> StoryProject:
        """
        Get a single story project by ID for the current user

        Args:
            project_id: UUID of the project

        Returns:
            StoryProject object

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        project_data = db.story_projects.find_one({
            '_id': project_id,
            'user_id': user_id
        })

        if not project_data:
            raise ValueError(f"Story project with ID {project_id} not found.")

        return StoryProject.from_dict(project_data)

    def get_projects(self) -> List[StoryProject]:
        """
        Get all story projects for the current user

        Returns:
            List of StoryProject objects
        """
        db = get_db()
        user_id = self._get_user_id()

        projects_data = db.story_projects.find({
            'user_id': user_id
        }).sort('created_at', -1)  # Most recent first

        return [StoryProject.from_dict(p) for p in projects_data]

    def create_project(self, name: str) -> StoryProject:
        """
        Create a new story project for the current user

        Args:
            name: Name of the story project

        Returns:
            Created StoryProject object
        """
        db = get_db()
        user_id = self._get_user_id()

        project_id = str(uuid.uuid4())
        project = StoryProject(
            id=project_id,
            name=name,
            user_id=user_id,
            status=StoryProject.STATUS_DRAFT_SETUP,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.story_projects.insert_one(project.to_dict())

        return project

    def update_status(self, project_id: str, status: str) -> StoryProject:
        """
        Update project status

        Args:
            project_id: UUID of the project
            status: New status value

        Returns:
            Updated StoryProject object

        Raises:
            ValueError: If project not found, doesn't belong to user, or invalid status
        """
        if status not in StoryProject.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        db = get_db()
        user_id = self._get_user_id()

        result = db.story_projects.update_one(
            {'_id': project_id, 'user_id': user_id},
            {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
        )

        if result.matched_count == 0:
            raise ValueError(f"Story project with ID {project_id} not found.")

        return self.get_project(project_id)

    def update_project(self, project_id: str, name: str = None,
                      child_profile_id: str = None,
                      character_bible_id: str = None,
                      story_state_id: str = None) -> StoryProject:
        """
        Update project fields

        Args:
            project_id: UUID of the project
            name: New name (optional)
            child_profile_id: Child profile ID (optional)
            character_bible_id: Character bible ID (optional)
            story_state_id: Story state ID (optional)

        Returns:
            Updated StoryProject object

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        update_fields = {'updated_at': datetime.utcnow()}
        if name is not None:
            update_fields['name'] = name
        if child_profile_id is not None:
            update_fields['child_profile_id'] = child_profile_id
        if character_bible_id is not None:
            update_fields['character_bible_id'] = character_bible_id
        if story_state_id is not None:
            update_fields['story_state_id'] = story_state_id

        result = db.story_projects.update_one(
            {'_id': project_id, 'user_id': user_id},
            {'$set': update_fields}
        )

        if result.matched_count == 0:
            raise ValueError(f"Story project with ID {project_id} not found.")

        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        """
        Delete a story project and all associated data

        Args:
            project_id: UUID of the project

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.story_projects.delete_one({
            '_id': project_id,
            'user_id': user_id
        })

        if result.deleted_count == 0:
            raise ValueError(f"Story project with ID {project_id} not found.")

        # Delete associated data
        db.child_profiles.delete_many({'project_id': project_id})
        db.character_assets.delete_many({'project_id': project_id})
        db.story_states.delete_many({'project_id': project_id})
        db.story_pages.delete_many({'project_id': project_id})
        db.chat_messages.delete_many({'project_id': project_id})
        db.images.delete_many({'project_id': project_id})
