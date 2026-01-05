"""
OpenAI Service - Wrapper for OpenAI API interactions
Handles story chat, text generation, and content moderation
"""
from typing import List, Dict, Any, Optional
import json
from openai import OpenAI
from src.utils.config import AppConfig

class OpenAIService:
    """
    Service for interacting with OpenAI API
    Used for story chat, compilation, and moderation
    """

    def __init__(self):
        self.client = OpenAI(api_key=AppConfig.OPENAI_API_KEY)
        self.default_model = "gpt-4o"  # Latest GPT-4 model
        self.moderation_model = "text-moderation-latest"

    def chat_completion(self, messages: List[Dict[str, str]],
                       model: str = None,
                       temperature: float = 0.7,
                       max_tokens: int = 2000,
                       response_format: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send a chat completion request to OpenAI

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (defaults to gpt-4o)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens in response
            response_format: Optional response format (e.g., {"type": "json_object"})

        Returns:
            Dictionary containing:
                - content: Response text
                - model: Model used
                - tokens_used: Total tokens consumed
                - structured_data: Parsed JSON if response_format was json_object
        """
        if not model:
            model = self.default_model

        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if response_format:
            request_params["response_format"] = response_format

        response = self.client.chat.completions.create(**request_params)

        result = {
            "content": response.choices[0].message.content,
            "model": response.model,
            "tokens_used": response.usage.total_tokens,
            "structured_data": None
        }

        # Parse JSON if response format was json_object
        if response_format and response_format.get("type") == "json_object":
            try:
                result["structured_data"] = json.loads(result["content"])
            except json.JSONDecodeError:
                # If parsing fails, leave structured_data as None
                pass

        return result

    def generate_story_state(self, conversation_history: List[Dict[str, str]],
                            child_name: str, child_age: int) -> Dict[str, Any]:
        """
        Generate structured story state from conversation

        Args:
            conversation_history: List of chat messages
            child_name: Name of the child
            child_age: Age of the child

        Returns:
            Dictionary with structured story data and response info
        """
        system_prompt = f"""You are a creative children's story writer helping to develop a personalized story for {child_name}, age {child_age}.

Based on the conversation, generate a structured story outline. Return your response as a JSON object with the following structure:
{{
  "title": "Story Title",
  "age_range": "3-5" or "6-8" or "9-12" based on child's age,
  "characters": [
    {{"name": "character name", "description": "character description", "role": "main/supporting"}}
  ],
  "setting": "Description of where the story takes place",
  "outline": ["Plot point 1", "Plot point 2", ...],
  "page_count": estimated number of pages (typically 8-16 for children's books),
  "themes": ["theme1", "theme2"],
  "tone": "adventurous/funny/heartwarming/educational/etc"
}}

Make sure the story is age-appropriate and includes {child_name} as the main character."""

        messages = [
            {"role": "system", "content": system_prompt},
            *conversation_history
        ]

        return self.chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.8
        )

    def compile_story_pages(self, story_state: Dict[str, Any],
                           child_name: str) -> Dict[str, Any]:
        """
        Compile finalized story pages with text and illustration descriptions

        Args:
            story_state: Structured story state dictionary
            child_name: Name of the child

        Returns:
            Dictionary with pages array and response info
        """
        system_prompt = f"""You are a children's book author. Convert the story outline into finalized pages.

For each page, provide:
1. Page text (1-3 sentences, appropriate for the age range)
2. Illustration description (detailed scene description for image generation)

Return as JSON:
{{
  "pages": [
    {{
      "page_number": 1,
      "page_text": "Text for the page",
      "illustration_prompt": "Detailed description of what should be illustrated",
      "scene_description": "Brief scene summary",
      "must_include": ["element1", "element2"],
      "must_avoid": ["scary elements", "inappropriate content"]
    }}
  ]
}}

Ensure {child_name} appears consistently across pages and the story matches the outline."""

        story_summary = json.dumps(story_state, indent=2)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the story outline:\n\n{story_summary}\n\nPlease generate the pages."}
        ]

        return self.chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=4000
        )

    def moderate_content(self, text: str) -> Dict[str, Any]:
        """
        Check content for policy violations using OpenAI moderation API

        Args:
            text: Text to moderate

        Returns:
            Dictionary with:
                - flagged: Boolean indicating if content was flagged
                - categories: Dictionary of flagged categories
                - category_scores: Dictionary of scores per category
        """
        response = self.client.moderations.create(
            model=self.moderation_model,
            input=text
        )

        result = response.results[0]

        return {
            "flagged": result.flagged,
            "categories": result.categories.model_dump(),
            "category_scores": result.category_scores.model_dump()
        }

    def enhance_illustration_prompt(self, base_prompt: str,
                                   character_bible: Dict[str, Any],
                                   style_notes: str = None) -> str:
        """
        Enhance an illustration prompt with character consistency details

        Args:
            base_prompt: Basic scene description
            character_bible: Character traits and visual details
            style_notes: Additional style guidance

        Returns:
            Enhanced prompt string
        """
        system_prompt = """You are an expert at writing prompts for AI image generation.
Given a scene description and character details, create a detailed image generation prompt
that ensures character consistency and visual quality.

Return only the enhanced prompt text, not JSON."""

        character_info = json.dumps(character_bible, indent=2)

        user_message = f"""Scene: {base_prompt}

Character Details:
{character_info}

{f'Style Notes: {style_notes}' if style_notes else ''}

Create a detailed image generation prompt."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        result = self.chat_completion(
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        return result["content"]
