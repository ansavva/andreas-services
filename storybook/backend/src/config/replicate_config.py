"""
Replicate Configuration Loader
Loads and manages Replicate SDXL model configuration from YAML file
"""
import yaml
from typing import Dict, Any, List, Optional
from .config import CONFIG_YAML_PATH


class ReplicateConfig:
    """
    Manages loading and accessing Replicate configuration from YAML
    """

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ReplicateConfig, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Load configuration from YAML file"""
        with open(CONFIG_YAML_PATH, 'r') as f:
            self._config = yaml.safe_load(f)

    def reload(self):
        """Reload configuration from file (useful for testing/hot-reload)"""
        self._load_config()

    # Account configuration
    def get_owner(self) -> str:
        """
        Get Replicate account owner/username

        Returns:
            Account owner username (default: 'ansavva')
        """
        training_models = self._config.get('models', {}).get('training_models', {})
        replicate_cfg = training_models.get('replicate', {})
        return replicate_cfg.get('owner', 'ansavva')

    def get_default_profile(self) -> str:
        """Return the default model profile identifier"""
        training_models = self._config.get('models', {}).get('training_models', {})
        replicate_cfg = training_models.get('replicate', {})
        default_profile = replicate_cfg.get('default_profile')
        profile_ids = self.get_profile_ids()
        if default_profile in profile_ids:
            return default_profile
        if profile_ids:
            return profile_ids[0]
        return "stability"

    def _get_profiles_map(self) -> Dict[str, Dict[str, Any]]:
        training_models = self._config.get('models', {}).get('training_models', {})
        replicate_cfg = training_models.get('replicate', {})
        return replicate_cfg.get('profiles', {})

    def get_profile_ids(self) -> List[str]:
        """List available profile identifiers"""
        return list(self._get_profiles_map().keys())

    def get_available_profiles(self) -> List[Dict[str, Any]]:
        """Return metadata for each available profile"""
        profiles = []
        for profile_id, cfg in self._get_profiles_map().items():
            profiles.append({
                "id": profile_id,
                "label": cfg.get("label", profile_id.title()),
                "description": cfg.get("description", "")
            })
        return profiles

    def get_model_name_template(self, profile: str = "stability") -> str:
        """
        Get the model name template (e.g., \"stability_{user_id}_{project_id}\")
        """
        section = self._get_profile_section(profile)
        return section.get("model_name_template", "{profile}_{user_id}_{project_id}")

    def build_model_name(self, profile: str, user_id: str, project_id: str) -> str:
        """
        Build a model name for Replicate using the configured template
        """
        template = self.get_model_name_template(profile)
        return template.format(
            profile=profile,
            user_id=str(user_id),
            project_id=str(project_id)
        )

    # Training configuration
    def _get_profile_section(self, profile: Optional[str]) -> Dict[str, Any]:
        profiles = self._get_profiles_map()
        if profile and profile in profiles:
            return profiles[profile]
        default_profile = self.get_default_profile()
        return profiles.get(default_profile, {})

    def get_training_config(self, profile: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Replicate training configuration

        Returns:
            Dictionary containing all training parameters from YAML
        """
        return self._get_profile_section(profile).get('training', {})

    def get_training_steps(self) -> int:
        """Get number of training steps (default: 1000)"""
        return self.get_training_config().get('steps', 1000)

    def get_learning_rate(self) -> float:
        """Get learning rate for training (default: 0.0004)"""
        return self.get_training_config().get('learning_rate', 0.0004)

    def get_batch_size(self) -> int:
        """Get training batch size (default: 1)"""
        return self.get_training_config().get('batch_size', 1)

    def get_resolution(self) -> str:
        """Get training resolutions (default: '512,768,1024')"""
        return self.get_training_config().get('resolution', '512,768,1024')

    def get_autocaption(self) -> bool:
        """Get autocaption setting (default: True)"""
        return self.get_training_config().get('autocaption', True)

    def get_caption_dropout_rate(self) -> float:
        """Get caption dropout rate (default: 0.05)"""
        return self.get_training_config().get('caption_dropout_rate', 0.05)

    def get_optimizer(self) -> str:
        """Get optimizer type (default: 'adamw8bit')"""
        return self.get_training_config().get('optimizer', 'adamw8bit')

    def get_trigger_word(self) -> str:
        """Get trigger word for model (default: None)"""
        return self.get_training_config().get('trigger_word')

    def get_token_string(self) -> str:
        """Get token string for SDXL training (default: 'TOK')"""
        return self.get_training_config().get('token_string', 'TOK')

    def get_is_lora(self) -> bool:
        """Get whether to use LoRA training (default: True)"""
        return self.get_training_config().get('is_lora', True)

    def get_unet_learning_rate(self) -> float:
        """Get U-Net learning rate for SDXL (default: 1e-06)"""
        return self.get_training_config().get('unet_learning_rate', 0.000001)

    def get_hardware(self) -> str:
        """Get hardware specification (default: 'gpu-t4')"""
        return self.get_training_config().get('hardware', 'gpu-t4')

    def get_visibility(self) -> str:
        """Get model visibility (default: 'private')"""
        return self.get_training_config().get('visibility', 'private')

    def get_trainer_version(self) -> str:
        """Get trainer model version"""
        return self.get_training_config().get(
            'trainer_version',
            'ostris/flux-dev-lora-trainer:4ffd32160efd92e956d39c5338a9b8fbafca58e03f791f6d8011f3e20e8ea6fa'
        )

    # Generation configuration
    def get_generation_config(self, profile: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Replicate generation configuration

        Returns:
            Dictionary containing all generation parameters from YAML
        """
        return self._get_profile_section(profile).get('generation', {})

    def profile_uses_subject_token(self, profile: str) -> bool:
        """Determine if a profile requires subject token injection"""
        return bool(self._get_profile_section(profile).get('use_subject_token'))


# Singleton instance
replicate_config = ReplicateConfig()
