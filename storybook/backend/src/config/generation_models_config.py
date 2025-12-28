"""
Generation Models Configuration Loader

Manages configuration for generation-based models that don't require training.
Supports multiple providers: Stability AI, Replicate (generation-only models like Flux Pro)
"""
import yaml
import io
from typing import Dict, Any, List, Optional, BinaryIO
from .config import CONFIG_YAML_PATH, ASSETS_DIR


class GenerationModelsConfig:
    """
    Manages loading and accessing generation model configurations from YAML

    Generation models directly generate images from prompts + reference images
    without requiring fine-tuning/training.
    """

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GenerationModelsConfig, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Load configuration from YAML file"""
        self.assets_dir = ASSETS_DIR
        with open(CONFIG_YAML_PATH, 'r') as f:
            self._config = yaml.safe_load(f)

    def reload(self):
        """Reload configuration from file (useful for testing/hot-reload)"""
        self._load_config()

    # ============================================
    # Provider and Profile Discovery
    # ============================================

    def get_providers(self) -> List[str]:
        """Get list of available generation model providers"""
        gen_models = self._config.get('models', {}).get('generation_models', {})
        return list(gen_models.keys())

    def get_default_provider(self) -> str:
        """Get default provider (defaults to stability_ai)"""
        providers = self.get_providers()
        return providers[0] if providers else "stability_ai"

    def _get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for a specific provider"""
        gen_models = self._config.get('models', {}).get('generation_models', {})
        if provider not in gen_models:
            raise ValueError(
                f"Invalid provider '{provider}'. "
                f"Available providers: {self.get_providers()}"
            )
        return gen_models[provider]

    def get_owner(self, provider: str) -> str:
        """Get owner/account for a provider"""
        return self._get_provider_config(provider).get('owner', '')

    def get_api_host(self, provider: str) -> Optional[str]:
        """Get API host URL for a provider"""
        return self._get_provider_config(provider).get('api_host')

    def get_default_engine(self, provider: str) -> Optional[str]:
        """Get default engine/model for a provider"""
        return self._get_provider_config(provider).get('default_engine')

    def get_endpoint(self, provider: str, endpoint_name: str, **kwargs) -> str:
        """
        Get API endpoint URL for a provider

        Args:
            provider: Provider name
            endpoint_name: Endpoint name (e.g., 'text_to_image', 'image_to_image', 'style_transfer')
            **kwargs: Variables to format into the endpoint path (e.g., engine='sdxl')

        Returns:
            Full URL for the endpoint
        """
        provider_config = self._get_provider_config(provider)
        api_host = provider_config.get('api_host', '')
        endpoints = provider_config.get('endpoints', {})
        endpoint_path = endpoints.get(endpoint_name, '')

        # Format path with any provided variables
        if kwargs:
            endpoint_path = endpoint_path.format(**kwargs)

        return f"{api_host}{endpoint_path}"

    def get_default_profile(self, provider: str) -> str:
        """Get default profile for a provider"""
        provider_cfg = self._get_provider_config(provider)
        default_profile = provider_cfg.get('default_profile')
        profile_ids = self.get_profile_ids(provider)

        if default_profile and default_profile in profile_ids:
            return default_profile
        if profile_ids:
            return profile_ids[0]

        return "default"

    def _get_profiles_map(self, provider: str) -> Dict[str, Dict[str, Any]]:
        """Get all profiles for a provider"""
        provider_cfg = self._get_provider_config(provider)
        return provider_cfg.get('profiles', {})

    def get_profile_ids(self, provider: str) -> List[str]:
        """List available profile identifiers for a provider"""
        return list(self._get_profiles_map(provider).keys())

    def get_available_profiles(self, provider: str) -> List[Dict[str, Any]]:
        """
        Get metadata for all available profiles for a provider

        Returns:
            List of dicts with keys: id, label, description, method
        """
        profiles = []
        for profile_id, cfg in self._get_profiles_map(provider).items():
            profiles.append({
                "id": profile_id,
                "label": cfg.get("label", profile_id.title()),
                "description": cfg.get("description", ""),
                "method": cfg.get("method", "generation")
            })
        return profiles

    def _get_profile_section(self, provider: str, profile: Optional[str]) -> Dict[str, Any]:
        """Get configuration section for a specific profile"""
        profiles = self._get_profiles_map(provider)
        if profile and profile in profiles:
            return profiles[profile]
        default_profile = self.get_default_profile(provider)
        return profiles.get(default_profile, {})

    # ============================================
    # Generation Configuration
    # ============================================

    def get_generation_config(self, provider: str, profile: Optional[str] = None) -> Dict[str, Any]:
        """
        Get generation configuration for a provider/profile

        Args:
            provider: Provider name (e.g., 'stability_ai', 'replicate')
            profile: Profile name (e.g., 'style_transfer', 'flux_pro')

        Returns:
            Dictionary containing all generation parameters
        """
        return self._get_profile_section(provider, profile).get('generation', {})

    def get_method(self, provider: str, profile: Optional[str] = None) -> str:
        """
        Get generation method for a profile

        Returns:
            Method name (e.g., 'style_transfer', 'image_to_image', 'text_to_image')
        """
        return self._get_profile_section(provider, profile).get('method', 'generation')

    def get_reference_image_requirements(self, provider: str, profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get reference image requirements for a profile

        Returns:
            Dict with keys: required (bool), min (int), max (int), description (str)
            or None if not specified
        """
        return self._get_profile_section(provider, profile).get('reference_images')

    def get_model_id(self, provider: str, profile: Optional[str] = None) -> Optional[str]:
        """
        Get model ID for Replicate models

        Returns:
            Model ID string (e.g., 'black-forest-labs/flux-1.1-pro') or None
        """
        return self._get_profile_section(provider, profile).get('model')

    # ============================================
    # Prompt Template Management
    # ============================================

    def _load_prompt_file(self, filepath: str) -> str:
        """Load a prompt from a markdown file in assets directory"""
        full_path = self.assets_dir / filepath

        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")

        with open(full_path, 'r') as f:
            content = f.read().strip()

        return content

    def get_prompt_template(self, provider: str, profile: Optional[str] = None) -> Optional[str]:
        """
        Get prompt template content for a profile

        Returns:
            Prompt template string or None if not configured
        """
        gen_cfg = self.get_generation_config(provider, profile)
        template_key = gen_cfg.get('prompt_template')

        if not template_key:
            return None

        # Load from prompts config
        prompts_cfg = self._config.get('prompts', {})
        if template_key in prompts_cfg:
            return self._load_prompt_file(prompts_cfg[template_key])

        return None

    def get_negative_prompt_template(self, provider: str, profile: Optional[str] = None) -> Optional[str]:
        """
        Get negative prompt template content for a profile

        Returns:
            Negative prompt template string or None if not configured
        """
        gen_cfg = self.get_generation_config(provider, profile)
        template_key = gen_cfg.get('negative_prompt_template')

        if not template_key:
            return None

        # Load from prompts config
        prompts_cfg = self._config.get('prompts', {})
        if template_key in prompts_cfg:
            return self._load_prompt_file(prompts_cfg[template_key])

        return None

    def build_prompt(self, provider: str, profile: Optional[str] = None,
                    user_description: Optional[str] = None) -> str:
        """
        Build complete prompt from template + user description

        Args:
            provider: Provider name
            profile: Profile name
            user_description: Optional user-provided description to append

        Returns:
            Complete prompt string
        """
        template = self.get_prompt_template(provider, profile)

        if not template:
            return user_description or ""

        if user_description and user_description.strip():
            return f"{template}, {user_description.strip()}"

        return template

    def build_negative_prompt(self, provider: str, profile: Optional[str] = None,
                             must_avoid: Optional[List[str]] = None) -> str:
        """
        Build negative prompt from template + additional items to avoid

        Args:
            provider: Provider name
            profile: Profile name
            must_avoid: Optional list of additional items to avoid

        Returns:
            Complete negative prompt string
        """
        template = self.get_negative_prompt_template(provider, profile)

        if not template:
            template = ""

        if must_avoid:
            items = [template] if template else []
            items.extend(must_avoid)
            return ", ".join(items)

        return template

    # ============================================
    # Style Reference Management
    # ============================================

    def get_style_reference_id(self, provider: str, profile: Optional[str] = None) -> Optional[str]:
        """
        Get default style reference ID for a profile

        Returns:
            Style reference ID (e.g., 'animated_3d') or None
        """
        gen_cfg = self.get_generation_config(provider, profile)
        return gen_cfg.get('default_style_reference')

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

    def get_style_image(self, style_id: str) -> BinaryIO:
        """
        Load and return style reference image

        Args:
            style_id: Style identifier (e.g., 'animated_3d')

        Returns:
            BytesIO object containing image data

        Raises:
            ValueError: If style_id is invalid
            FileNotFoundError: If style image file doesn't exist
        """
        filename = self.get_style_reference_filename(style_id)

        if not filename:
            available = list(self.get_all_style_references().keys())
            raise ValueError(
                f"Invalid style_id '{style_id}'. "
                f"Available styles: {available}"
            )

        styles_dir = self.assets_dir / "styles"
        filepath = styles_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(
                f"Style reference image not found: {filepath}. "
                f"Please add the required style reference images to {styles_dir}"
            )

        # Read image into BytesIO
        with open(filepath, 'rb') as f:
            image_data = f.read()

        return io.BytesIO(image_data)

    # ============================================
    # Style Presets (for legacy Stability AI)
    # ============================================

    def get_style_preset(self, provider: str, profile: Optional[str] = None) -> Optional[str]:
        """
        Get default style preset for a profile

        Returns:
            Style preset name (e.g., '3d-model') or None
        """
        gen_cfg = self.get_generation_config(provider, profile)
        return gen_cfg.get('default_style_preset')

    def get_available_style_presets(self) -> List[str]:
        """Get list of all available Stability AI style presets"""
        return self._config.get('style_presets', [])

    def is_valid_style_preset(self, preset: str) -> bool:
        """Check if a style preset is valid"""
        return preset in self.get_available_style_presets()


# Singleton instance
generation_models_config = GenerationModelsConfig()
