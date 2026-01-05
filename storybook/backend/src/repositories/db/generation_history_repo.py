from flask import request
from typing import List, Optional
import uuid
from datetime import datetime

from src.repositories.db.database import get_db
from src.models.generation_history import GenerationHistory

class GenerationHistoryRepo:
    """
    Generation History repository - handles generation history metadata in MongoDB
    """

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def create(self, project_id: str, prompt: str, image_ids: List[str],
               reference_image_ids: List[str] = None,
               status: str = GenerationHistory.STATUS_COMPLETED,
               include_subject_description: Optional[bool] = None) -> GenerationHistory:
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
            include_subject_description=include_subject_description,
            status=status,
            created_at=datetime.utcnow()
        )

        db.generation_history.insert_one(history.to_dict())

        return history

    def get_draft_by_project(self, project_id: str) -> Optional[GenerationHistory]:
        """Get the active draft generation history for a project."""
        db = get_db()
        user_id = self._get_user_id()

        history_data = db.generation_history.find_one({
            'project_id': str(project_id),
            'user_id': user_id,
            'status': GenerationHistory.STATUS_DRAFT
        })

        if not history_data:
            return None

        return GenerationHistory.from_dict(history_data)

    def get_or_create_draft(self, project_id: str) -> GenerationHistory:
        """Fetch an existing draft or create a new one for a project."""
        existing = self.get_draft_by_project(project_id)
        if existing:
            return existing

        return self.create(
            project_id=project_id,
            prompt="",
            image_ids=[],
            reference_image_ids=[],
            status=GenerationHistory.STATUS_DRAFT,
            include_subject_description=None,
        )

    def add_reference_images_to_draft(self, project_id: str, image_ids: List[str]) -> GenerationHistory:
        """Ensure a draft exists and append reference images to it."""
        if not image_ids:
            return self.get_or_create_draft(project_id)

        draft = self.get_or_create_draft(project_id)
        db = get_db()
        user_id = self._get_user_id()

        db.generation_history.update_one(
            {"_id": draft.id, "user_id": user_id},
            {
                "$addToSet": {"reference_image_ids": {"$each": image_ids}},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        return self.get_by_id(draft.id)

    def remove_reference_images_from_draft(self, project_id: str, image_ids: List[str]) -> Optional[GenerationHistory]:
        """Remove reference images from the draft generation history."""
        if not image_ids:
            return self.get_draft_by_project(project_id)

        draft = self.get_draft_by_project(project_id)
        if not draft:
            return None

        db = get_db()
        user_id = self._get_user_id()

        db.generation_history.update_one(
            {"_id": draft.id, "user_id": user_id},
            {
                "$pull": {"reference_image_ids": {"$in": image_ids}},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        return self.get_by_id(draft.id)

    def finalize_draft(self, draft_id: str, prompt: str, image_ids: List[str],
                       reference_image_ids: Optional[List[str]] = None,
                       include_subject_description: Optional[bool] = None) -> GenerationHistory:
        """Promote a draft to a completed history entry."""
        db = get_db()
        user_id = self._get_user_id()

        update = {
            "prompt": prompt,
            "image_ids": image_ids,
            "status": GenerationHistory.STATUS_COMPLETED,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if reference_image_ids is not None:
            update["reference_image_ids"] = reference_image_ids
        if include_subject_description is not None:
            update["include_subject_description"] = include_subject_description

        db.generation_history.update_one(
            {"_id": draft_id, "user_id": user_id},
            {"$set": update},
        )
        return self.get_by_id(draft_id)

    def update_draft_prompt(
        self,
        project_id: str,
        prompt: str,
        include_subject_description: Optional[bool] = None,
    ) -> GenerationHistory:
        """Ensure a draft exists and update its prompt."""
        draft = self.get_or_create_draft(project_id)
        db = get_db()
        user_id = self._get_user_id()

        update_fields = {
            "prompt": prompt,
            "updated_at": datetime.utcnow(),
        }
        if include_subject_description is not None:
            update_fields["include_subject_description"] = include_subject_description

        db.generation_history.update_one(
            {"_id": draft.id, "user_id": user_id},
            {
                "$set": update_fields,
            },
        )
        return self.get_by_id(draft.id)

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

    def list_by_project(self, project_id: str, include_drafts: bool = False) -> List[GenerationHistory]:
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
        query = {
            'project_id': project_id,
            'user_id': user_id
        }
        if not include_drafts:
            query['status'] = {'$ne': GenerationHistory.STATUS_DRAFT}

        cursor = db.generation_history.find(query).sort('created_at', -1)  # -1 for descending order

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
