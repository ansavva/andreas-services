"""
Configuration Loader
Loads and manages configuration from YAML file
"""
import yaml
import os
from typing import Dict, List, Any, Optional
from pathlib import Path

class Config:
    """
    Manages loading and accessing configuration
    """

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Load configuration from YAML file"""
        # Find config file - go up from src/config to backend/config
        current_dir = Path(__file__).parent
        config_path = current_dir.parent.parent / "config" / "config.yaml"
        self.assets_dir = current_dir.parent.parent / "assets"

        if not config_path.exists():
            raise FileNotFoundError(f"Config not found at {config_path}")

        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)

    def _load_prompt_file(self, filepath: str) -> str:
        """Load a prompt from a markdown file in assets directory"""
        full_path = self.assets_dir / filepath

        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")

        with open(full_path, 'r') as f:
            content = f.read().strip()

        return content

    def reload(self):
        """Reload configuration from file (useful for testing/hot-reload)"""
        self._load_config()

    # Style references
    def get_style_reference_filename(self, style_id: str) -> Optional[str]:
        """Get filename for a style reference image"""
        style_refs = self._config.get('style_references', {})
        style_config = style_refs.get(style_id)
        if style_config:
            return style_config.get('filename')
        return None

    def get_all_style_references(self) -> Dict[str, str]:
        """Get all style reference filenames"""
        style_refs = self._config.get('style_references', {})
        return {
            style_id: config.get('filename')
            for style_id, config in style_refs.items()
        }

    # Character prompts
    def get_character_base_prompt(self) -> str:
        """Get base prompt for character generation"""
        prompt_file = self._config['prompts']['character_base_prompt']
        return self._load_prompt_file(prompt_file)

    def get_character_negative_prompt(self) -> str:
        """Get negative prompt for character generation"""
        prompt_file = self._config['prompts']['character_negative_prompt']
        return self._load_prompt_file(prompt_file)

    def get_character_default_style(self) -> str:
        """Get default style preset for character generation (legacy)"""
        return self._config['character']['default_style_preset']

    def get_character_image_strength(self) -> float:
        """Get image strength parameter for character generation"""
        return self._config['character']['image_strength']

    # Story illustration prompts
    def get_story_negative_prompt_items(self) -> List[str]:
        """Get list of negative prompt items for story illustrations"""
        prompt_file = self._config['prompts']['story_negative_prompt']
        content = self._load_prompt_file(prompt_file)
        # Split by comma and strip whitespace
        return [item.strip() for item in content.split(',')]

    def get_story_image_strength(self) -> float:
        """Get image strength for story illustrations"""
        return self._config['story_illustrations']['image_strength']

    # Style transfer (recommended method)
    def get_style_transfer_prompt(self) -> str:
        """Get base prompt for style transfer"""
        prompt_file = self._config['prompts']['style_transfer_prompt']
        return self._load_prompt_file(prompt_file)

    def get_style_transfer_negative(self) -> str:
        """Get negative prompt for style transfer"""
        prompt_file = self._config['prompts']['style_transfer_negative']
        return self._load_prompt_file(prompt_file)

    def get_style_strength(self) -> float:
        """Get default style strength for style transfer"""
        return self._config['character']['style_strength']

    def get_default_style_id(self) -> str:
        """Get default style reference for style transfer"""
        return self._config['character']['default_style_reference']

    # Style presets
    def get_available_style_presets(self) -> List[str]:
        """Get list of all available style presets"""
        return self._config['style_presets']

    def is_valid_style_preset(self, style: str) -> bool:
        """Check if a style preset is valid"""
        return style in self.get_available_style_presets()

    def build_style_transfer_prompt(self, user_description: Optional[str] = None) -> str:
        """
        Build complete prompt for style transfer

        Args:
            user_description: User-provided additional description (optional)

        Returns:
            Complete prompt string for style transfer
        """
        base = self.get_style_transfer_prompt()

        if user_description and user_description.strip():
            # Append user description to base prompt
            return f"{base}, {user_description.strip()}"

        return base

    def build_character_prompt(self,
                               child_name: Optional[str] = None,
                               user_description: Optional[str] = None) -> str:
        """
        Build complete character generation prompt (legacy image-to-image)

        Args:
            child_name: Name of the child (optional)
            user_description: User-provided additional description (optional)

        Returns:
            Complete prompt string
        """
        base = self.get_character_base_prompt()

        parts = []

        # Add child name if provided
        if child_name:
            parts.append(f"Portrait of a smiling child named {child_name}")

        parts.append(base)

        # Add user description if provided
        if user_description and user_description.strip():
            parts.append(user_description.strip())

        return ", ".join(parts)

    def build_story_negative_prompt(self, must_avoid: Optional[List[str]] = None) -> str:
        """
        Build negative prompt for story illustration

        Args:
            must_avoid: Optional list of additional items to avoid

        Returns:
            Complete negative prompt string
        """
        negative_items = self.get_story_negative_prompt_items().copy()

        if must_avoid:
            negative_items.extend(must_avoid)

        return ", ".join(negative_items)


# Singleton instance
config = Config()

# Backwards compatibility alias
prompts_config = config
