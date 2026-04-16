from typing import List, Optional, Dict, Any
from flask import request
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.chat_message import ChatMessage


class ChatMessageRepo:
    """
    ChatMessage repository - handles CRUD operations for chat messages using DynamoDB.
    Table: STORYBOOK_CHAT_MESSAGES_TABLE  PK: message_id (S)
    GSI: project_id-sequence-index  PK: project_id (S), SK: sequence (S — ISO timestamp)
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_CHAT_MESSAGES_TABLE')

    def get_by_id(self, message_id: str) -> ChatMessage:
        """
        Get a single chat message by ID for the current user.

        Raises:
            ValueError: If message not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'message_id': message_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Chat message with ID {message_id} not found.")

        return ChatMessage.from_dict(item)

    def get_conversation(self, project_id: str, limit: int = None) -> List[ChatMessage]:
        """
        Get chat conversation for a project, ordered by sequence (ISO timestamp) ascending.

        Args:
            project_id: UUID of the story project
            limit: Optional limit on number of messages (most recent N)
        """
        user_id = self._get_user_id()
        table = self._table()

        resp = table.query(
            IndexName='project_id-sequence-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id),
            ScanIndexForward=True,  # ascending
        )

        messages = [ChatMessage.from_dict(m) for m in resp.get('Items', [])]

        if limit and len(messages) > limit:
            messages = messages[-limit:]

        return messages

    def get_conversation_for_openai(self, project_id: str, limit: int = None) -> List[Dict[str, str]]:
        """Get conversation in OpenAI format for API calls."""
        messages = self.get_conversation(project_id, limit)
        return [msg.to_openai_format() for msg in messages]

    def add_message(self, project_id: str, role: str, content: str,
                    model: str = None, tokens_used: int = None,
                    structured_data: Dict[str, Any] = None) -> ChatMessage:
        """
        Add a new message to the conversation.
        Uses ISO timestamp as the sequence value for GSI sort key.

        Raises:
            ValueError: If invalid role
        """
        if role not in ChatMessage.VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")

        user_id = self._get_user_id()
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        # Use ISO timestamp as sequence — preserves ordering without atomic counters
        sequence = now.isoformat()

        message = ChatMessage(
            id=message_id,
            project_id=project_id,
            user_id=user_id,
            role=role,
            content=content,
            sequence=sequence,
            model=model,
            tokens_used=tokens_used,
            structured_data=structured_data,
            created_at=now,
        )

        self._table().put_item(Item=message.to_dict())
        return message

    def add_user_message(self, project_id: str, content: str) -> ChatMessage:
        """Add a user message to the conversation."""
        return self.add_message(
            project_id=project_id,
            role=ChatMessage.ROLE_USER,
            content=content,
        )

    def add_assistant_message(self, project_id: str, content: str,
                               model: str = None, tokens_used: int = None,
                               structured_data: Dict[str, Any] = None) -> ChatMessage:
        """Add an assistant message to the conversation."""
        return self.add_message(
            project_id=project_id,
            role=ChatMessage.ROLE_ASSISTANT,
            content=content,
            model=model,
            tokens_used=tokens_used,
            structured_data=structured_data,
        )

    def add_system_message(self, project_id: str, content: str) -> ChatMessage:
        """Add a system message to the conversation."""
        return self.add_message(
            project_id=project_id,
            role=ChatMessage.ROLE_SYSTEM,
            content=content,
        )

    def clear_conversation(self, project_id: str) -> None:
        """Delete all messages for a project."""
        user_id = self._get_user_id()
        table = self._table()

        resp = table.query(
            IndexName='project_id-sequence-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id),
        )

        items = resp.get('Items', [])
        if not items:
            return

        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'message_id': item['message_id']})

    def get_message_count(self, project_id: str) -> int:
        """Get total message count for a project."""
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='project_id-sequence-index',
            KeyConditionExpression=Key('project_id').eq(project_id),
            FilterExpression=Attr('user_id').eq(user_id),
            Select='COUNT',
        )

        return resp.get('Count', 0)
