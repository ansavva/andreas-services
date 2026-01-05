"""
Character Generation Service - Business logic for character image generation

This service contains application-specific logic for generating character portraits,
scenes, and story illustrations. It orchestrates calls to the underlying API proxies
(StabilityService, ReplicateService) with business context.
"""
from typing import List, Dict, Any, Optional, BinaryIO
from src.services.external.stability_service import StabilityService
from src.utils.config.generation_models_config import generation_models_config
from src.services.prompt_service import PromptService


class CharacterGenerationService:
    """
    Business logic for character image generation

    Handles application-specific workflows like:
    - Character portraits from reference photos
    - Preview scenes with character context
    - Story page illustrations with character consistency
    """

    def __init__(self):
        self.stability_proxy = StabilityService()
        self.prompt_service = PromptService()

    def generate_character_portrait(self,
                                   reference_images: List[BinaryIO],
                                   child_name: Optional[str] = None,
                                   user_description: Optional[str] = None,
                                   style: Optional[str] = None,
                                   profile: str = "stable_image") -> Dict[str, Any]:
        """
        Generate a stylized character portrait from reference photos

        Args:
            reference_images: List of child photos (file-like objects)
            child_name: Optional name of the child
            user_description: Optional custom description to add to prompt
            style: Optional style preset for generation (validates against allowed presets)
            profile: Generation profile to use (default: "stable_image")

        Returns:
            Dictionary with image_data and metadata

        Raises:
            ValueError: If style preset is invalid
        """
        provider = "stability_ai"
        gen_config = generation_models_config.get_generation_config(provider, profile)

        # Validate and set style preset
        if style is None:
            style = generation_models_config.get_style_preset(provider, profile)
        elif not generation_models_config.is_valid_style_preset(style):
            raise ValueError(
                f"Invalid style preset: {style}. "
                f"Must be one of: {generation_models_config.get_available_style_presets()}"
            )

        # Build prompt from config
        prompt = self.prompt_service.build_character_portrait_prompt(
            provider,
            profile,
            child_name,
            user_description,
        )

        negative_prompt = self.prompt_service.get_negative_prompt(provider, profile)
        image_strength = gen_config.get('image_strength', 0.35)

        # Call the API proxy
        return self.stability_proxy.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            style_preset=style,
            init_image=reference_images[0] if reference_images else None,
            image_strength=image_strength
        )

    def generate_preview_scene(self,
                              scene_name: str,
                              character_description: str,
                              reference_image: BinaryIO = None,
                              style: Optional[str] = None,
                              profile: str = "stable_image") -> Dict[str, Any]:
        """
        Generate a preview scene with the character

        Args:
            scene_name: Name of the scene (e.g., "park", "space", "pirate")
            character_description: Description of the character for consistency
            reference_image: Optional character reference image
            style: Optional style preset (validates against allowed presets)
            profile: Generation profile to use (default: "stable_image")

        Returns:
            Dictionary with image_data and metadata

        Raises:
            ValueError: If style preset is invalid
        """
        provider = "stability_ai"

        # Validate and set style preset
        if style is None:
            style = generation_models_config.get_style_preset(provider, profile)
        elif not generation_models_config.is_valid_style_preset(style):
            raise ValueError(
                f"Invalid style preset: {style}. "
                f"Must be one of: {generation_models_config.get_available_style_presets()}"
            )

        # Build scene prompt (business logic)
        prompt = self.prompt_service.build_preview_scene_prompt(scene_name, character_description)
        negative_prompt = self.prompt_service.get_negative_prompt(provider, profile)

        # Call the API proxy
        return self.stability_proxy.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            style_preset=style,
            init_image=reference_image,
            image_strength=0.3 if reference_image else 0.0
        )

    def generate_story_illustration(self,
                                   prompt: str,
                                   character_bible: Dict[str, Any] = None,
                                   character_reference: BinaryIO = None,
                                   must_avoid: List[str] = None,
                                   style: Optional[str] = None,
                                   profile: str = "stable_image") -> Dict[str, Any]:
        """
        Generate an illustration for a story page

        Args:
            prompt: Detailed scene description
            character_bible: Character traits and visual details
            character_reference: Character reference image
            must_avoid: List of elements to avoid
            style: Optional style preset (validates against allowed presets)
            profile: Generation profile to use (default: "stable_image")

        Returns:
            Dictionary with image_data and metadata

        Raises:
            ValueError: If style preset is invalid
        """
        provider = "stability_ai"

        # Validate and set style preset
        if style is None:
            style = generation_models_config.get_style_preset(provider, profile)
        elif not generation_models_config.is_valid_style_preset(style):
            raise ValueError(
                f"Invalid style preset: {style}. "
                f"Must be one of: {generation_models_config.get_available_style_presets()}"
            )

        # Enhance prompt with character consistency (business logic)
        full_prompt = self.prompt_service.build_story_illustration_prompt(
            prompt,
            character_bible,
        )

        negative_prompt = self.prompt_service.build_negative_prompt(
            provider,
            profile,
            must_avoid,
        )

        # Call the API proxy
        return self.stability_proxy.generate_image(
            prompt=full_prompt,
            negative_prompt=negative_prompt,
            style_preset=style,
            init_image=character_reference,
            image_strength=0.25 if character_reference else 0.0,
            width=1024,
            height=1024
        )

    def generate_stylized_portrait(self,
                                  init_image: BinaryIO,
                                  style_id: str,
                                  user_description: Optional[str] = None,
                                  style_strength: float = 0.7,
                                  profile: str = "style_transfer") -> bytes:
        """
        Generate a stylized portrait using style transfer

        Args:
            init_image: Child's reference photo
            style_id: Style reference ID (e.g., 'animated_3d')
            user_description: Optional user-provided description
            style_strength: How strongly to apply style (0.0-1.0)
            profile: Generation profile to use (default: "style_transfer")

        Returns:
            Raw image bytes

        Raises:
            ValueError: If style_id is invalid
        """
        provider = "stability_ai"

        # Load style reference image
        style_image = generation_models_config.get_style_image(style_id)

        # Build prompt
        prompt = self.prompt_service.build_provider_prompt(provider, profile, user_description)
        negative_prompt = self.prompt_service.get_negative_prompt(provider, profile)

        # Call the API proxy
        return self.stability_proxy.style_transfer(
            init_image=init_image,
            style_image=style_image,
            prompt=prompt,
            style_strength=style_strength,
            negative_prompt=negative_prompt,
            output_format="png"
        )
