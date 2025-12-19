"""
Prompts Configuration Loader
Loads and manages AI generation prompts from YAML configuration file
"""
import yaml
import os
from typing import Dict, List, Any, Optional
from pathlib import Path

class PromptsConfig:
    """
    Manages loading and accessing AI generation prompts from configuration
    """

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptsConfig, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Load prompts configuration from YAML file"""
        # Find config file - go up from src/config to backend/config
        current_dir = Path(__file__).parent
        config_path = current_dir.parent.parent / "config" / "prompts.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Prompts config not found at {config_path}")

        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)

    def reload(self):
        """Reload configuration from file (useful for testing/hot-reload)"""
        self._load_config()

    # Character prompts
    def get_character_base_prompt(self) -> str:
        """Get base prompt for character generation"""
        return self._config['character']['base_prompt']

    def get_character_negative_prompt(self) -> str:
        """Get negative prompt for character generation"""
        return self._config['character']['negative_prompt']

    def get_character_default_style(self) -> str:
        """Get default style preset for character generation"""
        return self._config['character']['default_style']

    def get_character_image_strength(self) -> float:
        """Get image strength parameter for character generation"""
        return self._config['character']['image_strength']

    # Preview scene prompts
    def get_scene_prompt(self, scene_name: str) -> Optional[str]:
        """Get prompt for a specific scene"""
        scenes = self._config['preview_scenes']['scenes']
        return scenes.get(scene_name)

    def get_all_scene_names(self) -> List[str]:
        """Get list of all available scene names"""
        return list(self._config['preview_scenes']['scenes'].keys())

    def get_scene_base_suffix(self) -> str:
        """Get base suffix added to all scene prompts"""
        return self._config['preview_scenes']['base_suffix']

    def get_scene_negative_prompt(self) -> str:
        """Get negative prompt for scene generation"""
        return self._config['preview_scenes']['negative_prompt']

    def get_scene_image_strength(self) -> float:
        """Get image strength for scene generation"""
        return self._config['preview_scenes']['image_strength']

    # Story illustration prompts
    def get_story_negative_prompt_items(self) -> List[str]:
        """Get list of negative prompt items for story illustrations"""
        return self._config['story_illustrations']['negative_prompt']

    def get_story_image_strength(self) -> float:
        """Get image strength for story illustrations"""
        return self._config['story_illustrations']['image_strength']

    # Style presets
    def get_available_style_presets(self) -> List[str]:
        """Get list of all available style presets"""
        return self._config['style_presets']

    def is_valid_style_preset(self, style: str) -> bool:
        """Check if a style preset is valid"""
        return style in self.get_available_style_presets()

    def build_character_prompt(self,
                               child_name: Optional[str] = None,
                               user_description: Optional[str] = None) -> str:
        """
        Build complete character generation prompt

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

    def build_scene_prompt(self,
                          scene_name: str,
                          character_description: str) -> str:
        """
        Build complete scene generation prompt

        Args:
            scene_name: Name of the scene
            character_description: Description of the character

        Returns:
            Complete prompt string
        """
        scene_desc = self.get_scene_prompt(scene_name)
        if not scene_desc:
            scene_desc = scene_name

        suffix = self.get_scene_base_suffix()

        return f"{character_description}, {scene_desc}, {suffix}"

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
prompts_config = PromptsConfig()
