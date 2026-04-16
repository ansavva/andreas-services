from typing import List
from flask import request
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.story_page import StoryPage


class StoryPageRepo:
    """
    StoryPage repository - handles CRUD operations for story pages using DynamoDB.
    Table: STORYBOOK_STORY_PAGES_TABLE  PK: page_id (S)
    GSI: project_id-page_number-index  PK: project_id (S), SK: page_number (N)
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_STORY_PAGES_TABLE')

    def get_by_project(self, project_id: str) -> List[StoryPage]:
        """Get all pages for a story project, ordered by page_number ascending."""
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='project_id-page_number-index',
            KeyConditionExpression=Key('project_id').eq(str(project_id)),
            FilterExpression=Attr('user_id').eq(user_id),
            ScanIndexForward=True,  # ascending by page_number
        )

        return [StoryPage.from_dict(page) for page in resp.get('Items', [])]

    def get_by_id(self, page_id: str) -> StoryPage:
        """
        Get a specific story page by ID for the current user.

        Raises:
            ValueError: If page not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'page_id': page_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Story page with ID {page_id} not found.")

        return StoryPage.from_dict(item)

    def create(self, project_id: str, page_number: int, page_text: str,
               illustration_prompt: str = None) -> StoryPage:
        """Create a new story page."""
        user_id = self._get_user_id()

        page = StoryPage(
            id=str(uuid.uuid4()),
            project_id=str(project_id),
            user_id=user_id,
            page_number=page_number,
            page_text=page_text,
            text_version=1,
            illustration_prompt=illustration_prompt,
            image_s3_key=None,
            image_version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=page.to_dict())
        return page

    def update_text(self, page_id: str, page_text: str) -> StoryPage:
        """
        Update page text and increment text_version.

        Raises:
            ValueError: If page not found
        """
        # Validates ownership and retrieves current version
        page = self.get_by_id(page_id)
        now = datetime.now(timezone.utc).isoformat()

        self._table().update_item(
            Key={'page_id': page_id},
            UpdateExpression='SET page_text = :page_text, text_version = :text_version, updated_at = :updated_at',
            ExpressionAttributeValues={
                ':page_text': page_text,
                ':text_version': page.text_version + 1,
                ':updated_at': now,
            },
        )

        return self.get_by_id(page_id)

    def update_prompt(self, page_id: str, illustration_prompt: str) -> StoryPage:
        """
        Update illustration prompt.

        Raises:
            ValueError: If page not found
        """
        # Validates ownership
        self.get_by_id(page_id)
        now = datetime.now(timezone.utc).isoformat()

        self._table().update_item(
            Key={'page_id': page_id},
            UpdateExpression='SET illustration_prompt = :illustration_prompt, updated_at = :updated_at',
            ExpressionAttributeValues={
                ':illustration_prompt': illustration_prompt,
                ':updated_at': now,
            },
        )

        return self.get_by_id(page_id)

    def update_image(self, page_id: str, image_s3_key: str) -> StoryPage:
        """
        Update page image and increment image_version.

        Raises:
            ValueError: If page not found
        """
        page = self.get_by_id(page_id)
        now = datetime.now(timezone.utc).isoformat()

        self._table().update_item(
            Key={'page_id': page_id},
            UpdateExpression='SET image_s3_key = :image_s3_key, image_version = :image_version, updated_at = :updated_at',
            ExpressionAttributeValues={
                ':image_s3_key': image_s3_key,
                ':image_version': page.image_version + 1,
                ':updated_at': now,
            },
        )

        return self.get_by_id(page_id)

    def delete(self, page_id: str) -> None:
        """
        Delete a story page.

        Raises:
            ValueError: If page not found
        """
        # Validates ownership
        self.get_by_id(page_id)
        self._table().delete_item(Key={'page_id': page_id})

    def delete_by_project(self, project_id: str) -> None:
        """Delete all pages for a project."""
        user_id = self._get_user_id()
        table = self._table()

        resp = table.query(
            IndexName='project_id-page_number-index',
            KeyConditionExpression=Key('project_id').eq(str(project_id)),
            FilterExpression=Attr('user_id').eq(user_id),
        )

        items = resp.get('Items', [])
        if not items:
            return

        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'page_id': item['page_id']})
