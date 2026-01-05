import json
import re
from typing import Any, Dict, List, Optional

from src.repositories.db.child_profile_repo import ChildProfileRepo
from src.repositories.db.story_page_repo import StoryPageRepo
from src.repositories.db.story_project_repo import StoryProjectRepo
from src.repositories.db.story_state_repo import StoryStateRepo
from src.services.external.openai_service import OpenAIService
from src.utils.config.chat_prompts_config import ChatPromptsConfig


class StoryChatService:
    """Story-specific workflows layered on top of chat."""

    def __init__(self) -> None:
        self.story_state_repo = StoryStateRepo()
        self.story_project_repo = StoryProjectRepo()
        self.child_profile_repo = ChildProfileRepo()
        self.story_page_repo = StoryPageRepo()
        self.openai_service = OpenAIService()
        self.chat_prompts_config = ChatPromptsConfig()

    def build_system_prompt(self, project_id: str) -> str:
        profile = self.child_profile_repo.get_by_project_id(project_id)
        if not profile:
            raise LookupError("Child profile not found. Please complete kid setup first.")

        template = self.chat_prompts_config.get_prompt("story_chat_system")
        return template.format(
            child_name=profile.child_name,
            child_age=profile.child_age,
        )

    def generate_story_state(self, project_id: str, conversation: List[Dict[str, str]]) -> Dict[str, Any]:
        profile = self.child_profile_repo.get_by_project_id(project_id)
        if not profile:
            raise LookupError("Child profile not found")

        if len(conversation) < 2:
            raise ValueError("Not enough conversation to generate story state")

        result = self.openai_service.generate_story_state(
            conversation_history=conversation,
            child_name=profile.child_name,
            child_age=profile.child_age,
        )

        if not result["structured_data"]:
            raise RuntimeError("Failed to generate structured story state")

        story_data = result["structured_data"]

        story_state = self.story_state_repo.create_or_update(
            project_id=project_id,
            title=story_data.get("title"),
            age_range=story_data.get("age_range"),
            characters=story_data.get("characters"),
            setting=story_data.get("setting"),
            outline=story_data.get("outline"),
            page_count=story_data.get("page_count"),
            themes=story_data.get("themes"),
            tone=story_data.get("tone"),
        )

        self.story_project_repo.update_project(
            project_id=project_id,
            story_state_id=story_state.id,
        )

        return {
            "story_state": story_state.to_dict(),
            "tokens_used": result["tokens_used"],
        }

    def get_story_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        story_state = self.story_state_repo.get_current(project_id)
        if not story_state:
            return None
        return story_state.to_dict()

    def get_story_state_versions(self, project_id: str) -> List[Dict[str, Any]]:
        versions = self.story_state_repo.get_all_versions(project_id)
        return [v.to_dict() for v in versions]

    def compile_story(self, project_id: str, conversation: List[Dict[str, str]]) -> Dict[str, Any]:
        story_state = self.story_state_repo.get_current(project_id)
        if not story_state:
            raise ValueError("Story state must be generated first")

        if not story_state.page_count or story_state.page_count == 0:
            raise ValueError("Story state must have page count")

        compile_prompt = (
            f"Based on our conversation, please generate the final story with exactly {story_state.page_count} pages.\n\n"
            "For each page, provide:\n"
            "1. Page number\n"
            "2. Text content (1-3 sentences appropriate for a "
            f"{story_state.age_range} child)\n"
            "3. Illustration description (detailed visual description for image generation)\n\n"
            "Format your response as JSON:\n"
            "{\n"
            '  "pages": [\n'
            "    {\n"
            '      "page_number": 1,\n'
            '      "text": "...",\n'
            '      "illustration_description": "..."\n'
            "    },\n"
            "    ...\n"
            "  ]\n"
            "}\n\n"
            "Story details:\n"
            f"- Title: {story_state.title}\n"
            f"- Characters: {', '.join([c.get('name', '') for c in (story_state.characters or [])])}\n"
            f"- Setting: {story_state.setting}\n"
            f"- Outline: {', '.join(story_state.outline or [])}"
        )

        compile_messages = conversation + [{"role": "user", "content": compile_prompt}]

        response = self.openai_service.chat_completion(
            messages=compile_messages,
            temperature=0.7,
        )

        pages_list = self._parse_pages_from_response(response["content"])
        if not pages_list:
            raise RuntimeError("Failed to parse story pages from AI response")

        self.story_page_repo.delete_by_project(project_id)

        created_pages = []
        for page_data in pages_list:
            page = self.story_page_repo.create(
                project_id=project_id,
                page_number=page_data.get("page_number"),
                page_text=page_data.get("text"),
                illustration_prompt=page_data.get("illustration_description"),
            )
            created_pages.append(page.to_dict())

        self.story_project_repo.update_status(project_id, "ILLUSTRATING")

        return {
            "message": "Story compiled successfully",
            "pages": created_pages,
        }

    def _parse_pages_from_response(self, response_content: str) -> List[Dict[str, Any]]:
        try:
            pages_data = json.loads(response_content)
            return pages_data.get("pages", [])
        except json.JSONDecodeError:
            json_match = re.search(r"\{[\s\S]*\}", response_content)
            if not json_match:
                return []
            pages_data = json.loads(json_match.group())
            return pages_data.get("pages", [])
