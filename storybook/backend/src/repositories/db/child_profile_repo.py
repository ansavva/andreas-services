from typing import Optional
from flask import request
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.child_profile import ChildProfile


class ChildProfileRepo:
    """
    ChildProfile repository - handles CRUD operations for child profiles using DynamoDB.
    Table: STORYBOOK_CHILD_PROFILES_TABLE  PK: profile_id (S)
    GSI: project_id-index  PK: project_id (S)
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_CHILD_PROFILES_TABLE')

    def get_by_project_id(self, project_id: str) -> Optional[ChildProfile]:
        """
        Get child profile by project ID for the current user.
        """
        user_id = self._get_user_id()
        table = self._table()

        resp = table.query(
            IndexName='project_id-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id),
        )

        items = resp.get('Items', [])
        if not items:
            return None

        return ChildProfile.from_dict(items[0])

    def get_by_id(self, profile_id: str) -> ChildProfile:
        """
        Get a single child profile by ID for the current user.

        Raises:
            ValueError: If profile not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'profile_id': profile_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Child profile with ID {profile_id} not found.")

        return ChildProfile.from_dict(item)

    def create(self, project_id: str, child_name: str, child_age: int,
               consent_given: bool, photo_ids: Optional[list] = None) -> ChildProfile:
        """Create a new child profile for a story project."""
        user_id = self._get_user_id()

        profile_id = str(uuid.uuid4())
        profile = ChildProfile(
            id=profile_id,
            project_id=project_id,
            user_id=user_id,
            child_name=child_name,
            child_age=child_age,
            consent_given=consent_given,
            consent_timestamp=datetime.now(timezone.utc) if consent_given else None,
            photo_ids=photo_ids or [],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=profile.to_dict())
        return profile

    def update(self, profile_id: str, child_name: str = None, child_age: int = None,
               photo_ids: list = None) -> ChildProfile:
        """
        Update a child profile.

        Raises:
            ValueError: If profile not found or doesn't belong to user
        """
        # Validates ownership
        self.get_by_id(profile_id)

        now = datetime.now(timezone.utc).isoformat()
        set_parts = ['updated_at = :updated_at']
        expr_values = {':updated_at': now}

        if child_name is not None:
            set_parts.append('child_name = :child_name')
            expr_values[':child_name'] = child_name
        if child_age is not None:
            set_parts.append('child_age = :child_age')
            expr_values[':child_age'] = child_age
        if photo_ids is not None:
            set_parts.append('photo_ids = :photo_ids')
            expr_values[':photo_ids'] = photo_ids

        self._table().update_item(
            Key={'profile_id': profile_id},
            UpdateExpression='SET ' + ', '.join(set_parts),
            ExpressionAttributeValues=expr_values,
        )

        return self.get_by_id(profile_id)

    def delete(self, profile_id: str) -> None:
        """
        Delete a child profile.

        Raises:
            ValueError: If profile not found or doesn't belong to user
        """
        # Validates ownership
        self.get_by_id(profile_id)
        self._table().delete_item(Key={'profile_id': profile_id})
