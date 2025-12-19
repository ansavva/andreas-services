from typing import Optional
from flask import request
import uuid
from datetime import datetime

from src.data.database import get_db
from src.models.child_profile import ChildProfile

class ChildProfileRepo:
    """
    ChildProfile repository - handles CRUD operations for child profiles using MongoDB
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_by_project_id(self, project_id: str) -> Optional[ChildProfile]:
        """
        Get child profile by project ID for the current user

        Args:
            project_id: UUID of the story project

        Returns:
            ChildProfile object or None if not found

        Raises:
            ValueError: If profile doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        profile_data = db.child_profiles.find_one({
            'project_id': project_id,
            'user_id': user_id
        })

        if not profile_data:
            return None

        return ChildProfile.from_dict(profile_data)

    def get_by_id(self, profile_id: str) -> ChildProfile:
        """
        Get a single child profile by ID for the current user

        Args:
            profile_id: UUID of the child profile

        Returns:
            ChildProfile object

        Raises:
            ValueError: If profile not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        profile_data = db.child_profiles.find_one({
            '_id': profile_id,
            'user_id': user_id
        })

        if not profile_data:
            raise ValueError(f"Child profile with ID {profile_id} not found.")

        return ChildProfile.from_dict(profile_data)

    def create(self, project_id: str, child_name: str, child_age: int,
               consent_given: bool, photo_ids: Optional[list] = None) -> ChildProfile:
        """
        Create a new child profile for a story project

        Args:
            project_id: UUID of the story project
            child_name: Name of the child
            child_age: Age of the child
            consent_given: Whether consent was given
            photo_ids: List of uploaded image IDs (optional)

        Returns:
            Created ChildProfile object
        """
        db = get_db()
        user_id = self._get_user_id()

        profile_id = str(uuid.uuid4())
        profile = ChildProfile(
            id=profile_id,
            project_id=project_id,
            user_id=user_id,
            child_name=child_name,
            child_age=child_age,
            consent_given=consent_given,
            consent_timestamp=datetime.utcnow() if consent_given else None,
            photo_ids=photo_ids or [],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.child_profiles.insert_one(profile.to_dict())

        return profile

    def update(self, profile_id: str, child_name: str = None, child_age: int = None,
               photo_ids: list = None) -> ChildProfile:
        """
        Update a child profile

        Args:
            profile_id: UUID of the profile
            child_name: New name (optional)
            child_age: New age (optional)
            photo_ids: Updated list of photo IDs (optional)

        Returns:
            Updated ChildProfile object

        Raises:
            ValueError: If profile not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        update_fields = {'updated_at': datetime.utcnow()}
        if child_name is not None:
            update_fields['child_name'] = child_name
        if child_age is not None:
            update_fields['child_age'] = child_age
        if photo_ids is not None:
            update_fields['photo_ids'] = photo_ids

        result = db.child_profiles.update_one(
            {'_id': profile_id, 'user_id': user_id},
            {'$set': update_fields}
        )

        if result.matched_count == 0:
            raise ValueError(f"Child profile with ID {profile_id} not found.")

        return self.get_by_id(profile_id)

    def delete(self, profile_id: str) -> None:
        """
        Delete a child profile

        Args:
            profile_id: UUID of the profile

        Raises:
            ValueError: If profile not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.child_profiles.delete_one({
            '_id': profile_id,
            'user_id': user_id
        })

        if result.deleted_count == 0:
            raise ValueError(f"Child profile with ID {profile_id} not found.")
