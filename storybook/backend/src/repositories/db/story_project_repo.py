from typing import List, Optional
from flask import request
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.story_project import StoryProject


class StoryProjectRepo:
    """
    StoryProject repository - handles CRUD operations for story projects using DynamoDB.
    Table: STORYBOOK_STORY_PROJECTS_TABLE  PK: project_id (S)
    GSI: user_id-created_at-index  PK: user_id (S), SK: created_at (S)
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_STORY_PROJECTS_TABLE')

    def get_project(self, project_id: str) -> StoryProject:
        """
        Get a single story project by ID for the current user.

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'project_id': project_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Story project with ID {project_id} not found.")

        return StoryProject.from_dict(item)

    def get_projects(self) -> List[StoryProject]:
        """Get all story projects for the current user, most recent first."""
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='user_id-created_at-index',
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False,  # descending by created_at
        )

        return [StoryProject.from_dict(p) for p in resp.get('Items', [])]

    def create_project(self, name: str) -> StoryProject:
        """Create a new story project for the current user."""
        user_id = self._get_user_id()

        project_id = str(uuid.uuid4())
        project = StoryProject(
            id=project_id,
            name=name,
            user_id=user_id,
            status=StoryProject.STATUS_DRAFT_SETUP,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=project.to_dict())
        return project

    def update_status(self, project_id: str, status: str) -> StoryProject:
        """
        Update project status.

        Raises:
            ValueError: If project not found, doesn't belong to user, or invalid status
        """
        if status not in StoryProject.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        # Validates ownership
        self.get_project(project_id)

        now = datetime.now(timezone.utc).isoformat()
        self._table().update_item(
            Key={'project_id': project_id},
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': status, ':updated_at': now},
        )

        return self.get_project(project_id)

    def update_project(self, project_id: str, name: str = None,
                       child_profile_id: str = None,
                       character_bible_id: str = None,
                       story_state_id: str = None) -> StoryProject:
        """
        Update project fields.

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        # Validates ownership
        self.get_project(project_id)

        now = datetime.now(timezone.utc).isoformat()
        set_parts = ['updated_at = :updated_at']
        expr_values = {':updated_at': now}

        if name is not None:
            set_parts.append('#name = :name')
            expr_values[':name'] = name
        if child_profile_id is not None:
            set_parts.append('child_profile_id = :child_profile_id')
            expr_values[':child_profile_id'] = child_profile_id
        if character_bible_id is not None:
            set_parts.append('character_bible_id = :character_bible_id')
            expr_values[':character_bible_id'] = character_bible_id
        if story_state_id is not None:
            set_parts.append('story_state_id = :story_state_id')
            expr_values[':story_state_id'] = story_state_id

        expr_names = {'#name': 'name'} if name is not None else {}

        kwargs = dict(
            Key={'project_id': project_id},
            UpdateExpression='SET ' + ', '.join(set_parts),
            ExpressionAttributeValues=expr_values,
        )
        if expr_names:
            kwargs['ExpressionAttributeNames'] = expr_names

        self._table().update_item(**kwargs)
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        """
        Delete a story project and all associated data.

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        from src.repositories.db.child_profile_repo import ChildProfileRepo
        from src.repositories.db.character_asset_repo import CharacterAssetRepo
        from src.repositories.db.story_state_repo import StoryStateRepo
        from src.repositories.db.story_page_repo import StoryPageRepo
        from src.repositories.db.chat_message_repo import ChatMessageRepo
        from src.repositories.db.image_repo import ImageRepo

        # Validates ownership
        self.get_project(project_id)
        self._table().delete_item(Key={'project_id': project_id})

        # Delete associated data
        _delete_by_project_gsi(
            _table('STORYBOOK_CHILD_PROFILES_TABLE'),
            'project_id-index', 'project_id', project_id, 'profile_id'
        )
        _delete_by_project_gsi(
            _table('STORYBOOK_CHARACTER_ASSETS_TABLE'),
            'project_id-created_at-index', 'project_id', project_id, 'asset_id'
        )
        _delete_by_project_gsi(
            _table('STORYBOOK_STORY_STATES_TABLE'),
            'project_id-version-index', 'project_id', project_id, 'state_id'
        )
        _delete_by_project_gsi(
            _table('STORYBOOK_STORY_PAGES_TABLE'),
            'project_id-page_number-index', 'project_id', project_id, 'page_id'
        )
        _delete_by_project_gsi(
            _table('STORYBOOK_CHAT_MESSAGES_TABLE'),
            'project_id-sequence-index', 'project_id', project_id, 'message_id'
        )
        _delete_by_project_gsi(
            _table('STORYBOOK_IMAGES_TABLE'),
            'project_id-created_at-index', 'project_id', project_id, 'image_id'
        )


def _delete_by_project_gsi(table, index_name: str, pk_name: str,
                            pk_value: str, item_pk_name: str) -> None:
    """Helper: query a GSI by project_id and batch-delete all matching items."""
    from boto3.dynamodb.conditions import Key as _Key
    resp = table.query(
        IndexName=index_name,
        KeyConditionExpression=_Key(pk_name).eq(pk_value),
    )
    items = resp.get('Items', [])
    if not items:
        return
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={item_pk_name: item[item_pk_name]})
