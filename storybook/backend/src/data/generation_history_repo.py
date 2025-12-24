from flask import request
from typing import List
import uuid
from datetime import datetime

from src.data.database import get_db
from src.models.generation_history import GenerationHistory

class GenerationHistoryRepo:
    """
    Generation History repository - handles generation history metadata in MongoDB
    """

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def create(self, project_id: str, prompt: str, image_ids: List[str],
               reference_image_ids: List[str] = None) -> GenerationHistory:
        """
        Create a new generation history entry

        Args:
            project_id: UUID of the project
            prompt: The exact prompt submitted
            image_ids: List of image IDs generated from this prompt
            reference_image_ids: Optional list of reference image IDs used for generation

        Returns:
            Created GenerationHistory object
        """
        db = get_db()
        user_id = self._get_user_id()

        # Ensure project_id is a string
        project_id = str(project_id)

        history_id = str(uuid.uuid4())

        history = GenerationHistory(
            id=history_id,
            project_id=project_id,
            user_id=user_id,
            prompt=prompt,
            image_ids=image_ids,
            reference_image_ids=reference_image_ids,
            created_at=datetime.utcnow()
        )

        db.generation_history.insert_one(history.to_dict())

        return history

    def get_by_id(self, history_id: str) -> GenerationHistory:
        """
        Get generation history by ID

        Args:
            history_id: UUID of the history entry

        Returns:
            GenerationHistory object

        Raises:
            ValueError: If history not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        history_data = db.generation_history.find_one({
            '_id': history_id,
            'user_id': user_id
        })

        if not history_data:
            raise ValueError(f"Generation history with ID {history_id} not found.")

        return GenerationHistory.from_dict(history_data)

    def list_by_project(self, project_id: str) -> List[GenerationHistory]:
        """
        List all generation history entries for a project

        Args:
            project_id: UUID of the project

        Returns:
            List of GenerationHistory objects, sorted by created_at descending (newest first)
        """
        db = get_db()
        user_id = self._get_user_id()

        # Ensure project_id is a string
        project_id = str(project_id)

        # Find all history entries for this project and user, sorted by created_at desc
        cursor = db.generation_history.find({
            'project_id': project_id,
            'user_id': user_id
        }).sort('created_at', -1)  # -1 for descending order

        return [GenerationHistory.from_dict(doc) for doc in cursor]

    def delete(self, history_id: str) -> bool:
        """
        Delete a generation history entry

        Args:
            history_id: UUID of the history entry

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If history not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.generation_history.delete_one({
            '_id': history_id,
            'user_id': user_id
        })

        if result.deleted_count == 0:
            raise ValueError(f"Generation history with ID {history_id} not found.")

        return True

    def delete_by_project(self, project_id: str) -> int:
        """
        Delete all generation history entries for a project

        Args:
            project_id: UUID of the project

        Returns:
            Number of entries deleted
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.generation_history.delete_many({
            'project_id': str(project_id),
            'user_id': user_id
        })

        return result.deleted_count
