from flask import request
from typing import Optional, List
from datetime import datetime

from src.data.database import get_db
from src.models.user_profile import UserProfile

class UserProfileRepo:
    """
    UserProfile repository - handles user profile metadata in MongoDB
    """

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_or_create(self, user_id: Optional[str] = None) -> UserProfile:
        """
        Get user profile by user_id, or create if it doesn't exist
        If user_id is not provided, uses the current authenticated user

        Args:
            user_id: Cognito user ID (optional, defaults to current user)

        Returns:
            UserProfile object
        """
        db = get_db()
        target_user_id = user_id or self._get_user_id()

        profile_data = db.user_profiles.find_one({'_id': target_user_id})

        if profile_data:
            return UserProfile.from_dict(profile_data)

        # Create new profile if it doesn't exist
        profile = UserProfile(
            user_id=target_user_id,
            display_name=None,
            profile_image_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.user_profiles.insert_one(profile.to_dict())
        return profile

    def get_by_id(self, user_id: str) -> Optional[UserProfile]:
        """
        Get user profile by user_id (returns None if not found)

        Args:
            user_id: Cognito user ID

        Returns:
            UserProfile object or None
        """
        db = get_db()

        profile_data = db.user_profiles.find_one({'_id': user_id})

        if not profile_data:
            return None

        return UserProfile.from_dict(profile_data)

    def get_multiple(self, user_ids: List[str]) -> dict:
        """
        Get multiple user profiles by user_ids

        Args:
            user_ids: List of Cognito user IDs

        Returns:
            Dictionary mapping user_id -> UserProfile
        """
        db = get_db()

        profiles = db.user_profiles.find({'_id': {'$in': user_ids}})

        return {
            str(p['_id']): UserProfile.from_dict(p)
            for p in profiles
        }

    def update(self, display_name: Optional[str] = None,
               profile_image_id: Optional[str] = None) -> UserProfile:
        """
        Update the current user's profile

        Args:
            display_name: New display name (optional)
            profile_image_id: New profile image ID (optional)

        Returns:
            Updated UserProfile object
        """
        db = get_db()
        user_id = self._get_user_id()

        # Get or create profile first
        profile = self.get_or_create(user_id)

        # Build update data
        update_data = {
            'updated_at': datetime.utcnow()
        }

        if display_name is not None:
            update_data['display_name'] = display_name

        if profile_image_id is not None:
            update_data['profile_image_id'] = profile_image_id

        # Update in database
        db.user_profiles.update_one(
            {'_id': user_id},
            {'$set': update_data}
        )

        # Return updated profile
        return self.get_or_create(user_id)

    def delete(self) -> bool:
        """
        Delete the current user's profile

        Returns:
            True if deleted successfully
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.user_profiles.delete_one({'_id': user_id})

        return result.deleted_count > 0
