from typing import List, Optional, Dict, Any
from flask import request
import uuid
from datetime import datetime

from src.repositories.db.database import get_db
from src.models.chat_message import ChatMessage

class ChatMessageRepo:
    """
    ChatMessage repository - handles CRUD operations for chat messages using MongoDB
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_by_id(self, message_id: str) -> ChatMessage:
        """
        Get a single chat message by ID for the current user

        Args:
            message_id: UUID of the chat message

        Returns:
            ChatMessage object

        Raises:
            ValueError: If message not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        message_data = db.chat_messages.find_one({
            '_id': message_id,
            'user_id': user_id
        })

        if not message_data:
            raise ValueError(f"Chat message with ID {message_id} not found.")

        return ChatMessage.from_dict(message_data)

    def get_conversation(self, project_id: str, limit: int = None) -> List[ChatMessage]:
        """
        Get chat conversation for a project, ordered by sequence

        Args:
            project_id: UUID of the story project
            limit: Optional limit on number of messages to return (most recent)

        Returns:
            List of ChatMessage objects sorted by sequence
        """
        db = get_db()
        user_id = self._get_user_id()

        query = db.chat_messages.find({
            'project_id': project_id,
            'user_id': user_id
        }).sort('sequence', 1)

        if limit:
            # Get last N messages
            total_count = db.chat_messages.count_documents({
                'project_id': project_id,
                'user_id': user_id
            })
            skip_count = max(0, total_count - limit)
            query = query.skip(skip_count).limit(limit)

        return [ChatMessage.from_dict(m) for m in query]

    def get_conversation_for_openai(self, project_id: str, limit: int = None) -> List[Dict[str, str]]:
        """
        Get conversation in OpenAI format for API calls

        Args:
            project_id: UUID of the story project
            limit: Optional limit on number of messages

        Returns:
            List of message dictionaries in OpenAI format
        """
        messages = self.get_conversation(project_id, limit)
        return [msg.to_openai_format() for msg in messages]

    def add_message(self, project_id: str, role: str, content: str,
                   model: str = None, tokens_used: int = None,
                   structured_data: Dict[str, Any] = None) -> ChatMessage:
        """
        Add a new message to the conversation

        Args:
            project_id: UUID of the story project
            role: Message role (user, assistant, system)
            content: Message content
            model: Model used (for assistant messages)
            tokens_used: Token count (for assistant messages)
            structured_data: Optional structured response data

        Returns:
            Created ChatMessage object

        Raises:
            ValueError: If invalid role
        """
        if role not in ChatMessage.VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")

        db = get_db()
        user_id = self._get_user_id()

        # Get next sequence number
        last_message = db.chat_messages.find_one(
            {'project_id': project_id, 'user_id': user_id},
            sort=[('sequence', -1)]
        )
        next_sequence = 1 if not last_message else last_message['sequence'] + 1

        message_id = str(uuid.uuid4())
        message = ChatMessage(
            id=message_id,
            project_id=project_id,
            user_id=user_id,
            role=role,
            content=content,
            sequence=next_sequence,
            model=model,
            tokens_used=tokens_used,
            structured_data=structured_data,
            created_at=datetime.utcnow()
        )

        db.chat_messages.insert_one(message.to_dict())

        return message

    def add_user_message(self, project_id: str, content: str) -> ChatMessage:
        """
        Add a user message to the conversation

        Args:
            project_id: UUID of the story project
            content: User's message content

        Returns:
            Created ChatMessage object
        """
        return self.add_message(
            project_id=project_id,
            role=ChatMessage.ROLE_USER,
            content=content
        )

    def add_assistant_message(self, project_id: str, content: str,
                             model: str = None, tokens_used: int = None,
                             structured_data: Dict[str, Any] = None) -> ChatMessage:
        """
        Add an assistant message to the conversation

        Args:
            project_id: UUID of the story project
            content: Assistant's response content
            model: Model used for generation
            tokens_used: Token count
            structured_data: Optional structured response

        Returns:
            Created ChatMessage object
        """
        return self.add_message(
            project_id=project_id,
            role=ChatMessage.ROLE_ASSISTANT,
            content=content,
            model=model,
            tokens_used=tokens_used,
            structured_data=structured_data
        )

    def add_system_message(self, project_id: str, content: str) -> ChatMessage:
        """
        Add a system message to the conversation

        Args:
            project_id: UUID of the story project
            content: System message content

        Returns:
            Created ChatMessage object
        """
        return self.add_message(
            project_id=project_id,
            role=ChatMessage.ROLE_SYSTEM,
            content=content
        )

    def clear_conversation(self, project_id: str) -> None:
        """
        Delete all messages for a project

        Args:
            project_id: UUID of the story project
        """
        db = get_db()
        user_id = self._get_user_id()

        db.chat_messages.delete_many({
            'project_id': project_id,
            'user_id': user_id
        })

    def get_message_count(self, project_id: str) -> int:
        """
        Get total message count for a project

        Args:
            project_id: UUID of the story project

        Returns:
            Number of messages
        """
        db = get_db()
        user_id = self._get_user_id()

        return db.chat_messages.count_documents({
            'project_id': project_id,
            'user_id': user_id
        })
