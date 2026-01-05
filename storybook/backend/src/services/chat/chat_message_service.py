from typing import Any, Dict, List, Optional

from src.repositories.db.chat_message_repo import ChatMessageRepo
from src.services.external.openai_service import OpenAIService


class ChatMessageService:
    """General-purpose chat flow for any project."""

    def __init__(self) -> None:
        self.chat_message_repo = ChatMessageRepo()
        self.openai_service = OpenAIService()

    def get_messages(self, project_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        messages = self.chat_message_repo.get_conversation(project_id, limit)
        return [msg.to_dict() for msg in messages]

    def get_conversation_for_openai(
        self,
        project_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        return self.chat_message_repo.get_conversation_for_openai(project_id, limit)

    def send_message(
        self,
        project_id: str,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.8,
    ) -> Dict[str, Any]:
        if not user_message:
            raise ValueError("Message is required")

        moderation_result = self.openai_service.moderate_content(user_message)
        if moderation_result["flagged"]:
            raise PermissionError("moderation", moderation_result)

        if system_prompt:
            self._ensure_system_prompt(project_id, system_prompt)

        self.chat_message_repo.add_user_message(project_id, user_message)
        conversation = self.chat_message_repo.get_conversation_for_openai(project_id)

        ai_response = self.openai_service.chat_completion(
            messages=conversation,
            temperature=temperature,
        )

        response_moderation = self.openai_service.moderate_content(ai_response["content"])
        if response_moderation["flagged"]:
            ai_response = self.openai_service.chat_completion(
                messages=conversation,
                temperature=0.5,
            )

        self.chat_message_repo.add_assistant_message(
            project_id=project_id,
            content=ai_response["content"],
            model=ai_response["model"],
            tokens_used=ai_response["tokens_used"],
        )

        return {
            "message": ai_response["content"],
            "model": ai_response["model"],
            "tokens_used": ai_response["tokens_used"],
        }

    def clear_messages(self, project_id: str) -> None:
        self.chat_message_repo.clear_conversation(project_id)

    def _ensure_system_prompt(self, project_id: str, system_prompt: str) -> None:
        messages = self.chat_message_repo.get_conversation(project_id)
        system_messages = [msg for msg in messages if msg.role == "system"]
        if not system_messages or system_messages[-1].content != system_prompt:
            self.chat_message_repo.add_system_message(project_id, system_prompt)
