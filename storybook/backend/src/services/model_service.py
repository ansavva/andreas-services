"""
Model Service - Handles AI model training and generation
Orchestrates Replicate service for FLUX model operations
"""
from typing import Optional, Dict, Any, List
import re
from flask import request
from io import BytesIO
from werkzeug.datastructures import FileStorage

from src.models.image import Image
from src.models.training_run import TrainingRun
from src.models.model_project import ModelProject
from src.services.image_service import ImageService
from src.data.training_run_repo import TrainingRunRepo
from src.data.model_project_repo import ModelProjectRepo
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
        self.training_run_repo = TrainingRunRepo()
        self.model_project_repo = ModelProjectRepo()

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

    def _build_subject_token(self, project: ModelProject) -> str:
        """Generate a consistent token string based on subject name"""
        subject = (project.subject_name or "subject").lower()
        sanitized = "".join(ch if ch.isalnum() else "_" for ch in subject).strip("_")
        if not sanitized:
            sanitized = "subject"
        return f"{sanitized}_tok"

    def train(self,
             project_id: str,
             image_ids: List[str],
             config_override: Optional[Dict[str, Any]] = None) -> TrainingRun:
        """
        Train a FLUX model with specific images and create a training run record

        Args:
            project_id: Model project ID
            image_ids: List of image IDs to use for this training
            config_override: Optional dict to override specific config values from YAML
                           Example: {"steps": 1500, "learning_rate": 0.0005}

        Returns:
            TrainingRun object with training details
        """
        model_name = self.__get_model_name(project_id)
        project = self.model_project_repo.get_project(project_id)
        subject_token = self._build_subject_token(project)

        # Create a training run record BEFORE starting training
        training_run = self.training_run_repo.create(
            project_id=project_id,
            image_ids=image_ids
        )

        try:
            # Create ZIP of the specific training images
            zip_file_buffer = self.image_service.create_zip_from_images(image_ids)

            # Start training (config comes from YAML, with optional overrides)
            overrides = dict(config_override or {})
            overrides.setdefault("token_string", subject_token)
            overrides.setdefault("trigger_word", subject_token)

            replicate_training_id = self.replicate.train(
                model_name=model_name,
                training_data=zip_file_buffer,
                config_override=overrides
            )

            # Update training run with Replicate ID and set status to starting
            training_run = self.training_run_repo.set_replicate_id(
                training_run.id,
                replicate_training_id
            )
            training_run = self.training_run_repo.update_status(
                training_run.id,
                TrainingRun.STATUS_STARTING
            )

        except Exception as e:
            # Mark training as failed if it couldn't start
            self.training_run_repo.update_status(
                training_run.id,
                TrainingRun.STATUS_FAILED,
                error_message=str(e)
            )
            raise

        return training_run

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
        project = self.model_project_repo.get_project(project_id)
        subject_token = self._build_subject_token(project)
        model_name = self.__get_model_name(project_id)
        prompt_to_use = prompt
        if project.subject_name:
            pattern = re.compile(re.escape(project.subject_name), re.IGNORECASE)
            prompt_to_use = pattern.sub(subject_token, prompt_to_use)
        if subject_token.lower() not in prompt_to_use.lower():
            prompt_to_use = f"{subject_token}, {prompt_to_use}".strip(", ")

        # Generate image (config comes from YAML, with optional overrides)
        image_bytes = self.replicate.generate(
            prompt=prompt_to_use,
            model_name=model_name,
            config_override=config_override
        )

        # Convert bytes to file-like object
        image_data = BytesIO(image_bytes)
        file = FileStorage(image_data)

        # Upload to storage and create database record with image_type="generated"
        image = self.image_service.upload_image(project_id, file, "out.jpg", image_type="generated")

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

    def get_training_runs(self, project_id: str) -> List[TrainingRun]:
        """
        Get all training runs for a project

        Args:
            project_id: Model project ID

        Returns:
            List of TrainingRun objects (newest first)
        """
        return self.training_run_repo.list_by_project(project_id)

    def update_training_run_status(self, training_run_id: str) -> TrainingRun:
        """
        Update a training run's status by checking Replicate

        Args:
            training_run_id: Training run ID

        Returns:
            Updated TrainingRun object
        """
        training_run = self.training_run_repo.get_by_id(training_run_id)

        if not training_run.replicate_training_id:
            return training_run

        # Get status + error info from Replicate
        replicate_info = self.replicate.get_training_status_details(training_run.replicate_training_id)
        replicate_status = replicate_info["status"]
        error_message = replicate_info.get("error_message")

        should_update = replicate_status != training_run.status
        if not should_update and replicate_status == TrainingRun.STATUS_FAILED:
            if error_message and error_message != training_run.error_message:
                should_update = True

        if should_update:
            training_run = self.training_run_repo.update_status(
                training_run_id,
                replicate_status,
                error_message if replicate_status == TrainingRun.STATUS_FAILED else None
            )

        return training_run
