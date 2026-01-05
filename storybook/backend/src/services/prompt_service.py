from typing import Optional, List
import re

from src.models.model_project import ModelProject
from src.utils.config.generation_models_config import generation_models_config


class PromptService:
    """Builds generation prompts with optional subject context."""

    def build_with_subject_description(
        self,
        prompt: str,
        project: ModelProject,
        include_subject_description: Optional[bool],
    ) -> str:
        prompt_text = prompt.strip() if isinstance(prompt, str) else prompt
        if include_subject_description and project.subject_description:
            desc = project.subject_description.strip()
            if desc:
                return f"{prompt_text}\n\nSubject description: {desc}" if prompt_text else desc
        return prompt_text

    def build_provider_prompt(
        self,
        provider: str,
        profile: Optional[str],
        prompt: str,
    ) -> str:
        """Apply provider-specific prompt templates."""
        return generation_models_config.build_prompt(provider, profile, prompt)

    def get_negative_prompt(
        self,
        provider: str,
        profile: Optional[str],
    ) -> Optional[str]:
        """Return provider-specific negative prompt template, if any."""
        return generation_models_config.get_negative_prompt_template(provider, profile)

    def apply_subject_token(
        self,
        prompt: str,
        subject_name: Optional[str],
        subject_token: Optional[str],
    ) -> str:
        """Ensure the subject token is present, replacing subject name if needed."""
        if not subject_token:
            return prompt
        prompt_to_use = prompt
        if subject_name:
            pattern = re.compile(re.escape(subject_name), re.IGNORECASE)
            prompt_to_use = pattern.sub(subject_token, prompt_to_use)
        if subject_token.lower() not in prompt_to_use.lower():
            prompt_to_use = f"{subject_token}, {prompt_to_use}".strip(", ")
        return prompt_to_use

    def build_character_portrait_prompt(
        self,
        provider: str,
        profile: str,
        child_name: Optional[str],
        user_description: Optional[str],
    ) -> str:
        """Build prompt for character portraits."""
        template = generation_models_config.get_prompt_template(provider, profile)
        if child_name:
            prompt = f"Portrait of a smiling child named {child_name}, {template}"
        else:
            prompt = template or ""
        if user_description:
            prompt = f"{prompt}, {user_description}" if prompt else user_description
        return prompt

    def build_preview_scene_prompt(self, scene_name: str, character_description: str) -> str:
        """Build prompt for preview scenes."""
        return f"{character_description} in a {scene_name} setting"

    def build_story_illustration_prompt(
        self,
        prompt: str,
        character_bible: Optional[dict],
    ) -> str:
        """Build prompt for story illustrations with character context."""
        full_prompt = prompt
        if character_bible:
            character_desc = character_bible.get("visual_description", "")
            if character_desc:
                full_prompt = f"{character_desc}, {prompt}"
        return full_prompt

    def build_negative_prompt(
        self,
        provider: str,
        profile: str,
        must_avoid: Optional[List[str]] = None,
    ) -> str:
        """Build negative prompt with optional avoid list."""
        return generation_models_config.build_negative_prompt(provider, profile, must_avoid)
