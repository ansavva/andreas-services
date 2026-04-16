from flask import request
from typing import Optional, List
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from src.repositories.db.database import _table
from src.models.user_profile import UserProfile


class UserProfileRepo:
    """
    UserProfile repository - handles user profile metadata in DynamoDB.
    Table: STORYBOOK_USER_PROFILES_TABLE  PK: user_id (S)
    """

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_USER_PROFILES_TABLE')

    def get_or_create(self, user_id: Optional[str] = None) -> UserProfile:
        """
        Get user profile by user_id, or create if it doesn't exist.
        If user_id is not provided, uses the current authenticated user.
        """
        target_user_id = user_id or self._get_user_id()
        table = self._table()

        resp = table.get_item(Key={'user_id': target_user_id})
        item = resp.get('Item')

        if item:
            return UserProfile.from_dict(item)

        # Create new profile
        profile = UserProfile(
            user_id=target_user_id,
            display_name=None,
            profile_image_id=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        table.put_item(Item=profile.to_dict())
        return profile

    def get_by_id(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile by user_id (returns None if not found)."""
        resp = self._table().get_item(Key={'user_id': user_id})
        item = resp.get('Item')
        if not item:
            return None
        return UserProfile.from_dict(item)

    def get_multiple(self, user_ids: List[str]) -> dict:
        """
        Get multiple user profiles by user_ids.

        Returns:
            Dictionary mapping user_id -> UserProfile
        """
        if not user_ids:
            return {}

        result = {}
        for uid in user_ids:
            profile = self.get_by_id(uid)
            if profile:
                result[uid] = profile
        return result

    def update(self, display_name: Optional[str] = None,
               profile_image_id: Optional[str] = None) -> UserProfile:
        """
        Update the current user's profile.
        """
        user_id = self._get_user_id()
        # Ensure profile exists
        self.get_or_create(user_id)

        now = datetime.now(timezone.utc).isoformat()
        set_parts = ['updated_at = :updated_at']
        expr_values = {':updated_at': now}
        expr_names = {}

        if display_name is not None:
            set_parts.append('display_name = :display_name')
            expr_values[':display_name'] = display_name

        if profile_image_id is not None:
            set_parts.append('profile_image_id = :profile_image_id')
            expr_values[':profile_image_id'] = profile_image_id

        self._table().update_item(
            Key={'user_id': user_id},
            UpdateExpression='SET ' + ', '.join(set_parts),
            ExpressionAttributeValues=expr_values,
        )

        return self.get_or_create(user_id)

    def delete(self) -> bool:
        """Delete the current user's profile."""
        user_id = self._get_user_id()
        # Check existence first
        item = self.get_by_id(user_id)
        if not item:
            return False
        self._table().delete_item(Key={'user_id': user_id})
        return True
