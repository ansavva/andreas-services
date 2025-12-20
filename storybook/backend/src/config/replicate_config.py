"""
Replicate Configuration Loader
Loads and manages Replicate FLUX model configuration from YAML file
"""
import yaml
from typing import Dict, Any
from pathlib import Path


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
        # Find config file - go up from src/config to backend/config
        current_dir = Path(__file__).parent
        config_path = current_dir.parent.parent / "config" / "config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config not found at {config_path}")

        with open(config_path, 'r') as f:
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
        return self._config.get('replicate', {}).get('owner', 'ansavva')

    # Training configuration
    def get_training_config(self) -> Dict[str, Any]:
        """
        Get Replicate training configuration

        Returns:
            Dictionary containing all training parameters from YAML
        """
        return self._config.get('replicate', {}).get('training', {})

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
    def get_generation_config(self) -> Dict[str, Any]:
        """
        Get Replicate generation configuration

        Returns:
            Dictionary containing all generation parameters from YAML
        """
        return self._config.get('replicate', {}).get('generation', {})

    def get_model_type(self) -> str:
        """Get model type (default: 'dev')"""
        return self.get_generation_config().get('model', 'dev')

    def get_aspect_ratio(self) -> str:
        """Get output aspect ratio (default: '1:1')"""
        return self.get_generation_config().get('aspect_ratio', '1:1')

    def get_num_outputs(self) -> int:
        """Get number of outputs to generate (default: 1)"""
        return self.get_generation_config().get('num_outputs', 1)

    def get_output_format(self) -> str:
        """Get output format (default: 'jpg')"""
        return self.get_generation_config().get('output_format', 'jpg')

    def get_output_quality(self) -> int:
        """Get output quality 1-100 (default: 90)"""
        return self.get_generation_config().get('output_quality', 90)

    def get_lora_scale(self) -> float:
        """Get LoRA scale - strength of fine-tuning (default: 1.0)"""
        return self.get_generation_config().get('lora_scale', 1.0)

    def get_guidance_scale(self) -> float:
        """Get guidance scale - how strictly to follow prompt (default: 3.5)"""
        return self.get_generation_config().get('guidance_scale', 3.5)

    def get_prompt_strength(self) -> float:
        """Get prompt adherence strength (default: 0.8)"""
        return self.get_generation_config().get('prompt_strength', 0.8)

    def get_num_inference_steps(self) -> int:
        """Get number of denoising steps (default: 28)"""
        return self.get_generation_config().get('num_inference_steps', 28)

    def get_extra_lora_scale(self) -> float:
        """Get additional LoRA scaling (default: 1.0)"""
        return self.get_generation_config().get('extra_lora_scale', 1.0)

    def get_disable_safety_checker(self) -> bool:
        """Get safety checker setting (default: True)"""
        return self.get_generation_config().get('disable_safety_checker', True)


# Singleton instance
replicate_config = ReplicateConfig()
