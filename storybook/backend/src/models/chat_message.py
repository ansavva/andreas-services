from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class ChatMessage:
    """
    ChatMessage model - stores individual messages in the story chat conversation
    Used for OpenAI chat history and transcript display
    """
    id: str  # UUID
    project_id: str  # Reference to StoryProject
    user_id: str  # Cognito user ID (sub claim)

    # Message metadata
    role: str  # "user", "assistant", "system"
    content: str  # Message text content
    sequence: int  # Message order in conversation (1-indexed)

    # OpenAI metadata
    model: Optional[str] = None  # Model used for generation (for assistant messages)
    tokens_used: Optional[int] = None  # Token count (for assistant messages)

    # Structured data (optional - for assistant messages with structured responses)
    structured_data: Optional[Dict[str, Any]] = None  # JSON data if response included structured output

    created_at: Optional[datetime] = None

    # Valid roles
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"

    VALID_ROLES = [ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM]

    def to_dict(self):
        """Convert to dictionary for MongoDB storage"""
        return {
            '_id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'role': self.role,
            'content': self.content,
            'sequence': self.sequence,
            'model': self.model,
            'tokens_used': self.tokens_used,
            'structured_data': self.structured_data,
            'created_at': self.created_at or datetime.utcnow()
        }

    @staticmethod
    def from_dict(data: dict) -> 'ChatMessage':
        """Create ChatMessage from MongoDB document"""
        return ChatMessage(
            id=str(data.get('_id')),
            project_id=data.get('project_id'),
            user_id=data.get('user_id'),
            role=data.get('role'),
            content=data.get('content'),
            sequence=data.get('sequence'),
            model=data.get('model'),
            tokens_used=data.get('tokens_used'),
            structured_data=data.get('structured_data'),
            created_at=data.get('created_at')
        )

    def to_openai_format(self) -> Dict[str, str]:
        """
        Convert to OpenAI chat message format

        Returns:
            Dictionary with role and content keys
        """
        return {
            'role': self.role,
            'content': self.content
        }
