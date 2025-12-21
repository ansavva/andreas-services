from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Image:
    """
    Image model - represents an image belonging to a project
    Metadata stored in MongoDB, actual image file stored in S3
    """
    id: str  # UUID or MongoDB _id
    project_id: str  # Reference to Project
    user_id: str  # Cognito user ID (sub claim)
    s3_key: str  # S3 object key where the image is stored
    filename: str  # Original filename
    content_type: str  # MIME type (e.g., image/jpeg)
    size_bytes: int  # File size in bytes
    image_type: str = "training"  # Type: "training" or "generated"
    created_at: Optional[datetime] = None

    # Constants for image types
    TYPE_TRAINING = "training"
    TYPE_GENERATED = "generated"

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            's3_key': self.s3_key,
            'filename': self.filename,
            'content_type': self.content_type,
            'size_bytes': self.size_bytes,
            'image_type': self.image_type,
            'created_at': self.created_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'Image':
        """Create Image from MongoDB document"""
        return Image(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            s3_key=data.get('s3_key'),
            filename=data.get('filename'),
            content_type=data.get('content_type'),
            size_bytes=data.get('size_bytes'),
            image_type=data.get('image_type', 'training'),  # Default to training for backward compatibility
            created_at=data.get('created_at')
        )
