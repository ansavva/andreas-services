from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class TrainingRun:
    """
    TrainingRun model - represents an immutable training session
    Each run tracks the images used and the training status from Replicate

    Once created, training runs cannot be modified or deleted - they are historical records
    """
    id: str  # UUID for this training run
    project_id: str  # Model project this training belongs to
    user_id: str  # Cognito user ID (sub claim)
    replicate_training_id: Optional[str] = None  # Training ID from Replicate
    image_ids: List[str] = None  # IDs of images used in this training run
    status: str = "pending"  # Training status: pending, starting, processing, succeeded, failed, canceled
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None  # Error details if training failed

    # Valid status values (from Replicate)
    STATUS_PENDING = "pending"
    STATUS_STARTING = "starting"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"

    VALID_STATUSES = [
        STATUS_PENDING,
        STATUS_STARTING,
        STATUS_PROCESSING,
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_CANCELED
    ]

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'replicate_training_id': self.replicate_training_id,
            'image_ids': self.image_ids or [],
            'status': self.status,
            'created_at': self.created_at or datetime.utcnow(),
            'updated_at': self.updated_at or datetime.utcnow(),
            'completed_at': self.completed_at,
            'error_message': self.error_message
        }

    @staticmethod
    def from_dict(data: dict) -> 'TrainingRun':
        """Create TrainingRun from MongoDB document"""
        return TrainingRun(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            replicate_training_id=data.get('replicate_training_id'),
            image_ids=data.get('image_ids', []),
            status=data.get('status', 'pending'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            completed_at=data.get('completed_at'),
            error_message=data.get('error_message')
        )
