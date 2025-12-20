"""
Model Service - Handles AI model training and generation
Orchestrates Replicate service for FLUX model operations
"""
from typing import Optional, Dict, Any
from flask import request
from io import BytesIO
from werkzeug.datastructures import FileStorage

from src.models.image import Image
from src.services.image_service import ImageService
from src.proxies.replicate_service import ReplicateService


class ModelService:
    """
    Service for managing AI model training and image generation
    Wraps ReplicateService with user-specific model naming
    Configuration is loaded from config.yaml via ReplicateService
    """

    def __init__(self):
        self.image_service = ImageService()
        self.replicate = ReplicateService()  # Owner loaded from config.yaml

    def __get_model_name(self, project_id: str) -> str:
        """
        Generate model name based on user ID and project ID

        Args:
            project_id: Model project ID

        Returns:
            Model name in format: flux_{user_id}_{project_id}
        """
        user_id = request.cognito_claims['sub']
        return f"flux_{user_id}_{project_id}"

    def exists(self, project_id: str) -> bool:
        """
        Check if a trained model exists for this project

        Args:
            project_id: Model project ID

        Returns:
            True if model exists, False otherwise
        """
        model_name = self.__get_model_name(project_id)
        return self.replicate.model_exists(model_name)

    def train(self,
             project_id: str,
             config_override: Optional[Dict[str, Any]] = None) -> str:
        """
        Train a FLUX model with uploaded images

        Args:
            project_id: Model project ID
            config_override: Optional dict to override specific config values from YAML
                           Example: {"steps": 1500, "learning_rate": 0.0005}

        Returns:
            Training ID for status polling
        """
        model_name = self.__get_model_name(project_id)

        # Create ZIP of training images
        zip_file_buffer = self.image_service.create_zip(project_id)

        # Start training (config comes from YAML, with optional overrides)
        training_id = self.replicate.train(
            model_name=model_name,
            training_data=zip_file_buffer,
            config_override=config_override
        )

        return training_id

    def check_training_status(self, training_id: str) -> str:
        """
        Check the status of a training job

        Args:
            training_id: ID of the training job

        Returns:
            Status string (e.g., "starting", "processing", "succeeded", "failed")
        """
        return self.replicate.get_training_status(training_id)

    def generate(self,
                prompt: str,
                project_id: str,
                config_override: Optional[Dict[str, Any]] = None) -> Image:
        """
        Generate an image using the trained model

        Args:
            prompt: Text prompt for image generation
            project_id: Model project ID
            config_override: Optional dict to override specific config values from YAML
                           Example: {"aspect_ratio": "16:9", "guidance_scale": 4.0}

        Returns:
            Image object with metadata

        Raises:
            Exception: If generation or upload fails
        """
        model_name = self.__get_model_name(project_id)

        # Generate image (config comes from YAML, with optional overrides)
        image_bytes = self.replicate.generate(
            prompt=prompt,
            model_name=model_name,
            config_override=config_override
        )

        # Convert bytes to file-like object
        image_data = BytesIO(image_bytes)
        file = FileStorage(image_data)

        # Upload to storage and create database record
        image = self.image_service.upload_image(project_id, file, "out.jpg")

        return image

    def cancel_training(self, training_id: str) -> bool:
        """
        Cancel an in-progress training job

        Args:
            training_id: ID of the training job to cancel

        Returns:
            True if cancelled successfully, False otherwise
        """
        return self.replicate.cancel_training(training_id)
