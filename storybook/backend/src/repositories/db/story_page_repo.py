from typing import List
from flask import request
import uuid
from datetime import datetime

from src.repositories.db.database import get_db
from src.models.story_page import StoryPage

class StoryPageRepo:
    """
    StoryPage repository - handles CRUD operations for story pages using MongoDB
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_by_project(self, project_id: str) -> List[StoryPage]:
        """
        Get all pages for a story project, ordered by page_number

        Args:
            project_id: ID of the story project

        Returns:
            List of StoryPage objects
        """
        db = get_db()
        user_id = self._get_user_id()

        pages_data = db.story_pages.find({
            'project_id': str(project_id),
            'user_id': user_id
        }).sort('page_number', 1)  # Ascending order by page number

        return [StoryPage.from_dict(page) for page in pages_data]

    def get_by_id(self, page_id: str) -> StoryPage:
        """
        Get a specific story page by ID

        Args:
            page_id: ID of the page

        Returns:
            StoryPage object

        Raises:
            ValueError: If page not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        page_data = db.story_pages.find_one({
            '_id': page_id,
            'user_id': user_id
        })

        if not page_data:
            raise ValueError(f"Story page with ID {page_id} not found.")

        return StoryPage.from_dict(page_data)

    def create(
        self,
        project_id: str,
        page_number: int,
        page_text: str,
        illustration_prompt: str = None
    ) -> StoryPage:
        """
        Create a new story page

        Args:
            project_id: ID of the story project
            page_number: Page number in the story
            page_text: Text content of the page
            illustration_prompt: Optional prompt for illustration generation

        Returns:
            Created StoryPage object
        """
        db = get_db()
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.story_pages.insert_one(page.to_dict())

        return page

    def update_text(self, page_id: str, page_text: str) -> StoryPage:
        """
        Update page text and increment version

        Args:
            page_id: ID of the page
            page_text: New text content

        Returns:
            Updated StoryPage object

        Raises:
            ValueError: If page not found
        """
        db = get_db()
        user_id = self._get_user_id()

        # Get current page
        page = self.get_by_id(page_id)

        # Update text and increment version
        result = db.story_pages.update_one(
            {'_id': page_id, 'user_id': user_id},
            {
                '$set': {
                    'page_text': page_text,
                    'text_version': page.text_version + 1,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        if result.modified_count == 0:
            raise ValueError(f"Story page with ID {page_id} not found.")

        return self.get_by_id(page_id)

    def update_prompt(self, page_id: str, illustration_prompt: str) -> StoryPage:
        """
        Update illustration prompt

        Args:
            page_id: ID of the page
            illustration_prompt: New illustration prompt

        Returns:
            Updated StoryPage object

        Raises:
            ValueError: If page not found
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.story_pages.update_one(
            {'_id': page_id, 'user_id': user_id},
            {
                '$set': {
                    'illustration_prompt': illustration_prompt,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        if result.modified_count == 0:
            raise ValueError(f"Story page with ID {page_id} not found.")

        return self.get_by_id(page_id)

    def update_image(self, page_id: str, image_s3_key: str) -> StoryPage:
        """
        Update page image and increment image version

        Args:
            page_id: ID of the page
            image_s3_key: S3 key for the new image

        Returns:
            Updated StoryPage object

        Raises:
            ValueError: If page not found
        """
        db = get_db()
        user_id = self._get_user_id()

        # Get current page
        page = self.get_by_id(page_id)

        # Update image and increment version
        result = db.story_pages.update_one(
            {'_id': page_id, 'user_id': user_id},
            {
                '$set': {
                    'image_s3_key': image_s3_key,
                    'image_version': page.image_version + 1,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        if result.modified_count == 0:
            raise ValueError(f"Story page with ID {page_id} not found.")

        return self.get_by_id(page_id)

    def delete(self, page_id: str) -> None:
        """
        Delete a story page

        Args:
            page_id: ID of the page

        Raises:
            ValueError: If page not found
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.story_pages.delete_one({
            '_id': page_id,
            'user_id': user_id
        })

        if result.deleted_count == 0:
            raise ValueError(f"Story page with ID {page_id} not found.")

    def delete_by_project(self, project_id: str) -> None:
        """
        Delete all pages for a project

        Args:
            project_id: ID of the story project
        """
        db = get_db()
        user_id = self._get_user_id()

        db.story_pages.delete_many({
            'project_id': str(project_id),
            'user_id': user_id
        })
