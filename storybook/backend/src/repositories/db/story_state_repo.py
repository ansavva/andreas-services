from typing import List, Optional, Dict, Any
from flask import request
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.story_state import StoryState


class StoryStateRepo:
    """
    StoryState repository - handles CRUD operations for story states using DynamoDB.
    Supports versioning for iterative story development.
    Table: STORYBOOK_STORY_STATES_TABLE  PK: state_id (S)
    GSI: project_id-version-index  PK: project_id (S), SK: version (N)

    is_current is managed in Python via read-modify-write, since DynamoDB does not
    support multi-item transactions without a full transaction API.
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_STORY_STATES_TABLE')

    def get_by_id(self, state_id: str) -> StoryState:
        """
        Get a single story state by ID for the current user.

        Raises:
            ValueError: If state not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'state_id': state_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Story state with ID {state_id} not found.")

        return StoryState.from_dict(item)

    def get_current(self, project_id: str) -> Optional[StoryState]:
        """
        Get the current (latest) story state for a project.
        Implemented by querying all states for the project and returning the one
        with is_current=True.
        """
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='project_id-version-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id) & Attr('is_current').eq(True),
        )

        items = resp.get('Items', [])
        if not items:
            return None

        return StoryState.from_dict(items[0])

    def get_all_versions(self, project_id: str) -> List[StoryState]:
        """Get all versions of story state for a project, newest first."""
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='project_id-version-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id),
            ScanIndexForward=False,  # descending by version
        )

        return [StoryState.from_dict(s) for s in resp.get('Items', [])]

    def _mark_all_not_current(self, project_id: str) -> None:
        """Mark all states for a project as not current (read-modify-write)."""
        user_id = self._get_user_id()
        table = self._table()

        resp = table.query(
            IndexName='project_id-version-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id) & Attr('is_current').eq(True),
        )

        for item in resp.get('Items', []):
            table.update_item(
                Key={'state_id': item['state_id']},
                UpdateExpression='SET is_current = :false',
                ExpressionAttributeValues={':false': False},
            )

    def create_or_update(self, project_id: str, title: str = None,
                         age_range: str = None, characters: List[Dict[str, Any]] = None,
                         setting: str = None, outline: List[str] = None,
                         page_count: int = None, themes: List[str] = None,
                         tone: str = None) -> StoryState:
        """Create a new story state version and mark it as current."""
        user_id = self._get_user_id()

        current = self.get_current(project_id)
        next_version = 1 if not current else current.version + 1

        # Mark all previous versions as not current
        self._mark_all_not_current(project_id)

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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=state.to_dict())
        return state

    def update_fields(self, state_id: str, **kwargs) -> StoryState:
        """
        Update specific fields of the current story state.

        Raises:
            ValueError: If state not found, doesn't belong to user, or is not current
        """
        # Validates ownership
        current_state = self.get_by_id(state_id)
        if not current_state.is_current:
            raise ValueError(f"Story state with ID {state_id} not found or not current.")

        allowed_fields = ['title', 'age_range', 'characters', 'setting',
                          'outline', 'page_count', 'themes', 'tone']

        now = datetime.now(timezone.utc).isoformat()
        set_parts = ['updated_at = :updated_at']
        expr_values = {':updated_at': now}

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                set_parts.append(f'{key} = :{key}')
                expr_values[f':{key}'] = value

        self._table().update_item(
            Key={'state_id': state_id},
            UpdateExpression='SET ' + ', '.join(set_parts),
            ExpressionAttributeValues=expr_values,
        )

        return self.get_by_id(state_id)

    def revert_to_version(self, project_id: str, version: int) -> StoryState:
        """
        Revert to a previous version (makes it current).

        Raises:
            ValueError: If version not found
        """
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='project_id-version-index',
            KeyConditionExpression=(
                Key('project_id').eq(project_id) & Key('version').eq(version)
            ),
            FilterExpression=Attr('user_id').eq(user_id),
        )

        items = resp.get('Items', [])
        if not items:
            raise ValueError(f"Story state version {version} not found.")

        target_state_id = items[0]['state_id']

        # Mark all versions as not current
        self._mark_all_not_current(project_id)

        # Mark the target version as current
        now = datetime.now(timezone.utc).isoformat()
        self._table().update_item(
            Key={'state_id': target_state_id},
            UpdateExpression='SET is_current = :true, updated_at = :updated_at',
            ExpressionAttributeValues={':true': True, ':updated_at': now},
        )

        return self.get_by_id(target_state_id)

    def delete_all_for_project(self, project_id: str) -> None:
        """Delete all story states for a project."""
        user_id = self._get_user_id()
        table = self._table()

        resp = table.query(
            IndexName='project_id-version-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id),
        )

        items = resp.get('Items', [])
        if not items:
            return

        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'state_id': item['state_id']})
