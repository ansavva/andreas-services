"""
Replicate Service - Wrapper for Replicate API interactions
Handles FLUX model training and image generation using fine-tuned models
Configuration is loaded from config.yaml
"""
from typing import Optional, Dict, Any, BinaryIO
import replicate
import requests
from src.config.replicate_config import replicate_config


class ReplicateService:
    """
    Service for interacting with Replicate API
    Handles FLUX model training and image generation

    Reference: https://replicate.com/blog/fine-tune-flux
    """

    def __init__(self, owner: Optional[str] = None):
        """
        Initialize Replicate service

        Args:
            owner: Replicate account owner name (optional, uses config value if not provided)
        """
        self.config = replicate_config
        self.owner = owner or self.config.get_owner()

    def model_exists(self, model_name: str) -> bool:
        """
        Check if a model exists in Replicate

        Args:
            model_name: Name of the model to check

        Returns:
            True if model exists, False otherwise
        """
        try:
            replicate.models.get(f"{self.owner}/{model_name}")
            return True
        except:
            return False

    def create_model(self,
                    model_name: str,
                    description: str = "A fine-tuned FLUX.1 model",
                    visibility: Optional[str] = None,
                    hardware: Optional[str] = None) -> replicate.models.Model:
        """
        Create a new model in Replicate

        Args:
            model_name: Name for the model
            description: Model description
            visibility: "public" or "private" (uses config default if not provided)
            hardware: Hardware specification (uses config default if not provided)

        Returns:
            Created Replicate model
        """
        return replicate.models.create(
            owner=self.owner,
            name=model_name,
            visibility=visibility or self.config.get_visibility(),
            hardware=hardware or self.config.get_hardware(),
            description=description
        )

    def train(self,
             model_name: str,
             training_data: BinaryIO,
             config_override: Optional[Dict[str, Any]] = None) -> str:
        """
        Train a FLUX model with the provided images

        Args:
            model_name: Name of the model to train
            training_data: ZIP file containing training images
            config_override: Optional dict to override specific config values from YAML

        Returns:
            Training ID for status polling
        """
        # Get or create the model
        try:
            model = replicate.models.get(f"{self.owner}/{model_name}")
        except:
            model = self.create_model(model_name=model_name)

        # Start with config from YAML
        training_input = {
            "input_images": training_data,
            "steps": self.config.get_training_steps(),
            "learning_rate": self.config.get_learning_rate(),
            "batch_size": self.config.get_batch_size(),
            "resolution": self.config.get_resolution(),
            "autocaption": self.config.get_autocaption(),
            "caption_dropout_rate": self.config.get_caption_dropout_rate(),
            "optimizer": self.config.get_optimizer(),
        }

        # Add trigger word if configured
        trigger_word = self.config.get_trigger_word()
        if trigger_word:
            training_input["trigger_word"] = trigger_word

        # Apply any overrides
        if config_override:
            training_input.update(config_override)

        # Get trainer version from config
        trainer_version = self.config.get_trainer_version()

        # Start training
        training = replicate.trainings.create(
            version=trainer_version,
            input=training_input,
            destination=f"{model.owner}/{model.name}"
        )

        return training.id

    def get_training_status(self, training_id: str) -> str:
        """
        Get the status of a training job

        Args:
            training_id: ID of the training job

        Returns:
            Status string (e.g., "starting", "processing", "succeeded", "failed")
        """
        training = replicate.trainings.get(training_id)
        return training.status

    def generate(self,
                prompt: str,
                model_name: str,
                config_override: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Generate an image using a trained FLUX model

        Args:
            prompt: Text prompt for image generation
            model_name: Name of the trained model to use
            config_override: Optional dict to override specific config values from YAML

        Returns:
            Image data as bytes

        Raises:
            Exception: If image download fails
        """
        # Get the model
        model = replicate.models.get(f"{self.owner}/{model_name}")

        # Start with config from YAML
        generation_input = {
            "prompt": prompt,
            "model": self.config.get_model_type(),
            "aspect_ratio": self.config.get_aspect_ratio(),
            "num_outputs": self.config.get_num_outputs(),
            "output_format": self.config.get_output_format(),
            "output_quality": self.config.get_output_quality(),
            "lora_scale": self.config.get_lora_scale(),
            "guidance_scale": self.config.get_guidance_scale(),
            "prompt_strength": self.config.get_prompt_strength(),
            "num_inference_steps": self.config.get_num_inference_steps(),
            "extra_lora_scale": self.config.get_extra_lora_scale(),
            "disable_safety_checker": self.config.get_disable_safety_checker(),
        }

        # Apply any overrides
        if config_override:
            generation_input.update(config_override)

        # Run prediction
        output = replicate.run(
            f"{model.owner}/{model.name}:{model.latest_version.id}",
            input=generation_input
        )

        # Get the URL of the generated image
        image_url = output[0].url

        # Download the image
        response = requests.get(image_url)

        if response.status_code != 200:
            raise Exception(f"Failed to download generated image from Replicate: {response.status_code}")

        return response.content

    def cancel_training(self, training_id: str) -> bool:
        """
        Cancel an in-progress training job

        Args:
            training_id: ID of the training job to cancel

        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            training = replicate.trainings.get(training_id)
            training.cancel()
            return True
        except:
            return False
