from typing import List, Optional
from flask import request
import uuid
from datetime import datetime

from src.data.database import get_db
from src.models.training_run import TrainingRun

class TrainingRunRepo:
    """
    Training Run repository - handles CRUD operations for training runs
    Training runs are immutable once created - they represent historical training sessions
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def create(self, project_id: str, image_ids: List[str], replicate_training_id: Optional[str] = None) -> TrainingRun:
        """
        Create a new training run

        Args:
            project_id: UUID of the project
            image_ids: List of image IDs used in this training
            replicate_training_id: Optional Replicate training ID

        Returns:
            Created TrainingRun object
        """
        db = get_db()
        user_id = self._get_user_id()

        training_run_id = str(uuid.uuid4())

        training_run = TrainingRun(
            id=training_run_id,
            project_id=str(project_id),
            user_id=user_id,
            replicate_training_id=replicate_training_id,
            image_ids=image_ids,
            status=TrainingRun.STATUS_PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.training_runs.insert_one(training_run.to_dict())

        return training_run

    def get_by_id(self, training_run_id: str) -> TrainingRun:
        """
        Get a training run by ID

        Args:
            training_run_id: UUID of the training run

        Returns:
            TrainingRun object

        Raises:
            ValueError: If training run not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        training_run_data = db.training_runs.find_one({
            '_id': training_run_id,
            'user_id': user_id
        })

        if not training_run_data:
            raise ValueError(f"Training run with ID {training_run_id} not found.")

        return TrainingRun.from_dict(training_run_data)

    def get_by_replicate_id(self, replicate_training_id: str) -> Optional[TrainingRun]:
        """
        Get a training run by Replicate training ID

        Args:
            replicate_training_id: Replicate training ID

        Returns:
            TrainingRun object or None if not found
        """
        db = get_db()
        user_id = self._get_user_id()

        training_run_data = db.training_runs.find_one({
            'replicate_training_id': replicate_training_id,
            'user_id': user_id
        })

        if not training_run_data:
            return None

        return TrainingRun.from_dict(training_run_data)

    def list_by_project(self, project_id: str) -> List[TrainingRun]:
        """
        Get all training runs for a project (newest first)

        Args:
            project_id: UUID of the project

        Returns:
            List of TrainingRun objects
        """
        db = get_db()
        user_id = self._get_user_id()

        training_runs_data = db.training_runs.find({
            'project_id': str(project_id),
            'user_id': user_id
        }).sort('created_at', -1)  # Newest first

        return [TrainingRun.from_dict(tr) for tr in training_runs_data]

    def update_status(self, training_run_id: str, status: str, error_message: Optional[str] = None) -> TrainingRun:
        """
        Update training run status (this is the ONLY mutable field)

        Args:
            training_run_id: UUID of the training run
            status: New status
            error_message: Optional error message if failed

        Returns:
            Updated TrainingRun object

        Raises:
            ValueError: If training run not found or invalid status
        """
        if status not in TrainingRun.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {TrainingRun.VALID_STATUSES}")

        db = get_db()
        user_id = self._get_user_id()

        update_fields = {
            'status': status,
            'updated_at': datetime.utcnow()
        }

        # Set completed_at when training finishes (success or failure)
        if status in [TrainingRun.STATUS_SUCCEEDED, TrainingRun.STATUS_FAILED, TrainingRun.STATUS_CANCELED]:
            update_fields['completed_at'] = datetime.utcnow()

        if error_message:
            update_fields['error_message'] = error_message

        result = db.training_runs.update_one(
            {'_id': training_run_id, 'user_id': user_id},
            {'$set': update_fields}
        )

        if result.matched_count == 0:
            raise ValueError(f"Training run with ID {training_run_id} not found.")

        return self.get_by_id(training_run_id)

    def set_replicate_id(self, training_run_id: str, replicate_training_id: str) -> TrainingRun:
        """
        Set the Replicate training ID for a training run

        Args:
            training_run_id: UUID of the training run
            replicate_training_id: Replicate training ID

        Returns:
            Updated TrainingRun object
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.training_runs.update_one(
            {'_id': training_run_id, 'user_id': user_id},
            {'$set': {
                'replicate_training_id': replicate_training_id,
                'updated_at': datetime.utcnow()
            }}
        )

        if result.matched_count == 0:
            raise ValueError(f"Training run with ID {training_run_id} not found.")

        return self.get_by_id(training_run_id)

    def delete(self, training_run_id: str) -> None:
        """
        Delete a single training run that belongs to the current user.
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.training_runs.delete_one(
            {'_id': training_run_id, 'user_id': user_id}
        )

        if result.deleted_count == 0:
            raise ValueError(f"Training run with ID {training_run_id} not found.")

    def delete_by_project(self, project_id: str) -> int:
        """
        Delete all training runs for a project

        Args:
            project_id: UUID of the project

        Returns:
            Number of training runs deleted
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.training_runs.delete_many({
            'project_id': str(project_id),
            'user_id': user_id
        })

        return result.deleted_count
