"""
Replicate Service - Wrapper for Replicate API interactions
Handles SDXL model training and image generation using fine-tuned models
Also handles generation-only models like Flux Pro
Configuration is loaded from config.yaml
"""
from typing import Optional, Dict, Any, BinaryIO, List
import time
import replicate
import requests
from src.config.replicate_config import replicate_config
from src.config.generation_models_config import generation_models_config
from src.config.config import Config

API_BASE = "https://api.replicate.com/v1"


class ReplicateService:
    """
    Service for interacting with Replicate API
    Handles SDXL model training and image generation

    Reference: https://replicate.com/blog/fine-tune-sdxl
    """

    def __init__(self, owner: Optional[str] = None):
        """
        Initialize Replicate service

        Args:
            owner: Replicate account owner name (optional, uses config value if not provided)
        """
        self.config = replicate_config
        self.owner = owner or self.config.get_owner()
        self.api_token = Config.REPLICATE_API_TOKEN

    def _resolve_model_identifier(self, model_name: str):
        """Split a model identifier into owner/name"""
        if "/" in model_name:
            owner, name = model_name.split("/", 1)
            return owner, name
        return self.owner, model_name

    def model_exists(self, model_name: str) -> bool:
        """
        Check if a model exists in Replicate

        Args:
            model_name: Name of the model to check

        Returns:
            True if model exists, False otherwise
        """
        owner, resolved_name = self._resolve_model_identifier(model_name)
        try:
            replicate.models.get(f"{owner}/{resolved_name}")
            return True
        except:
            return False

    def create_model(self,
                    model_name: str,
                    description: str = "A fine-tuned SDXL model",
                    visibility: Optional[str] = None,
                    hardware: Optional[str] = None):
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
            visibility=visibility or "private",
            hardware=hardware or "gpu-t4",
            description=description
        )

    def train(self,
             model_name: str,
             training_data: BinaryIO,
             config_override: Optional[Dict[str, Any]] = None,
             profile: str = "stability") -> str:
        """
        Train an SDXL model with the provided images

        Args:
            model_name: Name of the model to train
            training_data: ZIP file containing training images
            config_override: Optional dict to override specific config values from YAML

        Returns:
            Training ID for status polling
        """
        # Get or create the model
        training_config = self.config.get_training_config(profile)

        try:
            model = replicate.models.get(f"{self.owner}/{model_name}")
        except:
            model = self.create_model(
                model_name=model_name,
                visibility=training_config.get("visibility"),
                hardware=training_config.get("hardware"),
                description=f"A fine-tuned {profile} model"
            )

        # Start with config from YAML
        training_input = {
            "input_images": training_data,
            "steps": training_config.get("steps", 1000),
            "learning_rate": training_config.get("learning_rate", 0.0001),
            "batch_size": training_config.get("batch_size", 1),
            "resolution": training_config.get("resolution", 768),
            "autocaption": training_config.get("autocaption", True),
            "caption_dropout_rate": training_config.get("caption_dropout_rate", 0.05),
            "optimizer": training_config.get("optimizer", "adamw8bit"),
            "token_string": training_config.get("token_string"),
            "is_lora": training_config.get("is_lora", True),
            "unet_learning_rate": training_config.get("unet_learning_rate", 0.000001),
            "input_images_filetype": "zip",
        }

        # Add trigger word if configured
        trigger_word = training_config.get("trigger_word")
        if trigger_word:
            training_input["trigger_word"] = trigger_word

        # Apply any overrides
        if config_override:
            training_input.update(config_override)

        # Get trainer version from config
        trainer_version = training_config.get("trainer_version")

        # Start training
        training = replicate.trainings.create(
            version=trainer_version,
            input=training_input,
            destination=f"{model.owner}/{model.name}"
        )

        return training.id

    def get_training_status_details(self, training_id: str) -> Dict[str, Any]:
        """
        Get details about a training job including status and error info

        Args:
            training_id: ID of the training job

        Returns:
            Dict with status and optional error_message
        """
        training = replicate.trainings.get(training_id)
        error_message = None

        if getattr(training, "error", None):
            error = training.error
            if isinstance(error, dict):
                error_message = error.get("message") or str(error)
            else:
                error_message = str(error)

        return {
            "status": training.status,
            "error_message": error_message
        }

    def get_training_status(self, training_id: str) -> str:
        """
        Get just the status string of a training job
        """
        return self.get_training_status_details(training_id)["status"]

    def generate(self,
                prompt: str,
                model_name: str,
                config_override: Optional[Dict[str, Any]] = None,
                profile: str = "stability") -> bytes:
        """
        Generate an image using a trained SDXL model

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
        owner, resolved_name = self._resolve_model_identifier(model_name)
        model = replicate.models.get(f"{owner}/{resolved_name}")

        # Start with config from YAML
        generation_config = self.config.get_generation_config(profile)

        generation_input = {
            "prompt": prompt,
            "model": generation_config.get("model", "dev"),
            "aspect_ratio": generation_config.get("aspect_ratio", "1:1"),
            "num_outputs": generation_config.get("num_outputs", 1),
            "output_format": generation_config.get("output_format", "jpg"),
            "output_quality": generation_config.get("output_quality", 90),
            "lora_scale": generation_config.get("lora_scale", 1.0),
            "guidance_scale": generation_config.get("guidance_scale", 3.5),
            "prompt_strength": generation_config.get("prompt_strength", 0.8),
            "num_inference_steps": generation_config.get("num_inference_steps", 28),
            "extra_lora_scale": generation_config.get("extra_lora_scale", 1.0),
            "disable_safety_checker": generation_config.get("disable_safety_checker", True),
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

    def delete_model(self, model_name: str) -> bool:
        """
        Delete a model from Replicate

        Args:
            model_name: Name of the model to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        owner, resolved_name = self._resolve_model_identifier(model_name)

        # Try HTTP API deletion that removes versions first
        if self._delete_model_via_http(owner, resolved_name):
            return True

        # Fallback to basic delete via Replicate client
        try:
            model = replicate.models.get(f"{owner}/{resolved_name}")
            model.delete()
            return True
        except:
            return False

    def _delete_model_via_http(self, owner: str, model_name: str) -> bool:
        """
        Delete model + versions using direct HTTP calls (mirrors working script)
        """
        if not self.api_token:
            return False

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }

        version_ids = self._list_versions(owner, model_name, headers)

        for version_id in reversed(version_ids):
            url = f"{API_BASE}/models/{owner}/{model_name}/versions/{version_id}"
            resp = requests.delete(url, headers=headers, timeout=30)
            if resp.status_code not in (200, 202, 204):
                return False
            time.sleep(0.1)

        url = f"{API_BASE}/models/{owner}/{model_name}"
        resp = requests.delete(url, headers=headers, timeout=30)
        return resp.status_code in (200, 202, 204)

    def _list_versions(self, owner: str, model_name: str, headers: Dict[str, str]) -> List[str]:
        """List all version IDs for a model using HTTP API"""
        version_ids: List[str] = []
        url = f"{API_BASE}/models/{owner}/{model_name}/versions"

        while url:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 404:
                return []
            if resp.status_code != 200:
                return []

            data = resp.json()
            for version in data.get("results", []):
                vid = version.get("id")
                if vid:
                    version_ids.append(vid)
            url = data.get("next")

        return version_ids

    def generate_with_model(self,
                           prompt: str,
                           profile: str = "flux_pro",
                           image_prompt: Optional[BinaryIO] = None,
                           config_override: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Generate an image using a generation-only model (no training required)

        This method is for models like Flux 1.1 Pro that don't require training
        and support direct generation with prompts and optional reference images.

        Args:
            prompt: Text prompt for image generation
            profile: Model profile to use (e.g., 'flux_pro')
            image_prompt: Optional reference image for guided composition
            config_override: Optional dict to override specific config values

        Returns:
            Image data as bytes

        Raises:
            Exception: If generation or image download fails
        """
        provider = "replicate"
        gen_config = generation_models_config.get_generation_config(provider, profile)
        model_id = generation_models_config.get_model_id(provider, profile)

        if not model_id:
            raise ValueError(f"No model ID configured for profile '{profile}'")

        # Build input parameters from config
        generation_input = {
            "prompt": prompt,
            "aspect_ratio": gen_config.get("aspect_ratio", "1:1"),
            "num_outputs": gen_config.get("num_outputs", 1),
            "output_format": gen_config.get("output_format", "png"),
            "output_quality": gen_config.get("output_quality", 90),
            "safety_tolerance": gen_config.get("safety_tolerance", 2),
            "prompt_upsampling": gen_config.get("prompt_upsampling", False),
        }

        # Add image prompt if provided
        if image_prompt:
            # Convert to URL or data URL (Replicate accepts image URLs)
            # For now, we'll need to upload it or provide it as data
            # This might need adjustment based on how you handle image uploads
            generation_input["image_prompt"] = image_prompt

        # Apply any overrides
        if config_override:
            generation_input.update(config_override)

        # Run prediction
        output = replicate.run(
            model_id,
            input=generation_input
        )

        # Handle output - could be a list of URLs or direct output
        if isinstance(output, list) and len(output) > 0:
            image_url = output[0] if isinstance(output[0], str) else output[0].url
        else:
            image_url = output.url if hasattr(output, 'url') else str(output)

        # Download the image
        response = requests.get(image_url)

        if response.status_code != 200:
            raise Exception(f"Failed to download generated image from Replicate: {response.status_code}")

        return response.content
