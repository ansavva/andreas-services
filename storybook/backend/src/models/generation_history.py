from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class GenerationHistory:
    """
    Generation History model - represents a prompt + generated images entry
    Immutable history of image generation for a project
    """
    id: str  # UUID or MongoDB _id
    project_id: str  # Reference to Project
    user_id: str  # Cognito user ID (sub claim) - the creator
    prompt: str  # The exact prompt submitted
    image_ids: List[str]  # List of Image IDs generated from this prompt
    created_at: Optional[datetime] = None
    reference_image_ids: Optional[List[str]] = None  # Reference images used for this generation
    include_subject_description: Optional[bool] = None
    prediction_id: Optional[str] = None
    provider: Optional[str] = None
    error_message: Optional[str] = None
    status: str = "completed"  # draft, processing, completed, failed, canceled

    STATUS_DRAFT = "draft"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    VALID_STATUSES = [
        STATUS_DRAFT,
        STATUS_PROCESSING,
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_CANCELED,
    ]

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        data = {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'prompt': self.prompt,
            'image_ids': self.image_ids,
            'created_at': self.created_at or datetime.utcnow(),
            'status': self.status,
        }
        if self.reference_image_ids is not None:
            data['reference_image_ids'] = self.reference_image_ids
        if self.include_subject_description is not None:
            data['include_subject_description'] = self.include_subject_description
        if self.prediction_id is not None:
            data['prediction_id'] = self.prediction_id
        if self.provider is not None:
            data['provider'] = self.provider
        if self.error_message is not None:
            data['error_message'] = self.error_message
        return data

    @staticmethod
    def from_dict(data: dict) -> 'GenerationHistory':
        """Create GenerationHistory from MongoDB document"""
        return GenerationHistory(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            prompt=data.get('prompt'),
            image_ids=data.get('image_ids', []),
            created_at=data.get('created_at'),
            reference_image_ids=data.get('reference_image_ids'),
            include_subject_description=data.get('include_subject_description'),
            prediction_id=data.get('prediction_id') or data.get('replicate_prediction_id'),
            provider=data.get('provider'),
            error_message=data.get('error_message'),
            status=data.get('status', GenerationHistory.STATUS_COMPLETED)
        )
