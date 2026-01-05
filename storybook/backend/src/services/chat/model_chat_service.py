from src.repositories.db.model_project_repo import ModelProjectRepo
from src.utils.config.chat_prompts_config import ChatPromptsConfig


class ModelChatService:
    """Model project chat-specific helpers."""

    def __init__(self) -> None:
        self.model_project_repo = ModelProjectRepo()
        self.chat_prompts_config = ChatPromptsConfig()

    def build_system_prompt(self, project_id: str) -> str:
        try:
            project = self.model_project_repo.get_project(project_id)
        except ValueError as exc:
            raise LookupError(str(exc)) from exc

        template = self.chat_prompts_config.get_prompt("model_chat_system")
        return template.format(
            project_name=project.name or "Untitled",
            subject_name=project.subject_name or "Unknown",
            subject_description=project.subject_description or "None provided",
            model_type=project.model_type or "default",
        )
