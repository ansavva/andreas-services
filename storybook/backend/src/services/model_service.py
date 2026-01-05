"""
Model Service - Handles AI model training and generation
Supports multiple Replicate profiles (e.g., Stability, Flux)
"""
from typing import Optional, Dict, Any, List
import re
import uuid
from flask import request
from io import BytesIO
from werkzeug.datastructures import FileStorage
import requests

from src.models.image import Image
from src.models.training_run import TrainingRun
from src.models.model_project import ModelProject
from src.models.generation_history import GenerationHistory
from src.services.image_service import ImageService
from src.repositories.db.training_run_repo import TrainingRunRepo
from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.services.external.replicate_service import ReplicateService
from src.services.external.stability_service import StabilityService
from src.utils.config.generation_models_config import generation_models_config


class ModelService:
    """
    Service for managing AI model training and image generation
    Wraps ReplicateService and StabilityService with user-specific model naming
    Configuration is loaded from config.yaml
    """

    def __init__(self):
        self.image_service = ImageService()
        self.replicate = ReplicateService()  # Owner loaded from config.yaml
        self.stability = StabilityService()  # Stability AI proxy
        self.training_run_repo = TrainingRunRepo()
        self.model_project_repo = ModelProjectRepo()
        self.generation_history_repo = GenerationHistoryRepo()

    def __get_model_name(self, project: ModelProject) -> str:
        """
        Generate model name based on user ID, project ID, and model profile.
        This returns the short name without owner prefix.
        """
        user_id = request.cognito_claims['sub']
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        return self.replicate.config.build_model_name(profile, user_id, project.id)

    def __get_model_identifier(self, project: ModelProject) -> str:
        """Return the stored owner/model identifier or fallback to short name"""
        if project.replicate_model_id:
            return project.replicate_model_id
        return self.__get_model_name(project)

    def ready(self, project_id: str) -> bool:
        """
        Check if a trained model is ready for this project

        Args:
            project_id: Model project ID

        Returns:
            True if model is ready, False otherwise
            For generation-only models, always returns True (no training needed)
        """
        project = self.model_project_repo.get_project(project_id)

        # For generation-only models, there's no trained model to check
        # They can generate immediately without training
        if not project.requires_training():
            return True
        model_identifier = self.__get_model_identifier(project)
        if project.status != ModelProject.STATUS_READY:
            return False

        return self.replicate.model_exists(model_identifier)

    def _build_subject_token(self, project: ModelProject) -> str:
        """Generate a consistent token string based on subject name"""
        subject = (project.subject_name or "subject").lower()
        sanitized = "".join(ch if ch.isalnum() else "_" for ch in subject).strip("_")
        if not sanitized:
            sanitized = "subject"
        return f"{sanitized}_tok"

    def train(self,
             project_id: str,
             image_ids: Optional[List[str]] = None,
             config_override: Optional[Dict[str, Any]] = None) -> TrainingRun:
        """
        Train an image model with specific images and create a training run record

        Args:
            project_id: Model project ID
            image_ids: Optional list of image IDs to use for this training.
                      If omitted, the current draft training run is used.
            config_override: Optional dict to override specific config values from YAML
                           Example: {"steps": 1500, "learning_rate": 0.0005}

        Returns:
            TrainingRun object with training details
        """
        project = self.model_project_repo.get_project(project_id)
        model_name = self.__get_model_name(project)
        model_identifier = f"{self.replicate.owner}/{model_name}"
        if project.replicate_model_id != model_identifier:
            self.model_project_repo.update_project(
                project_id,
                replicate_model_id=model_identifier
            )
            project.replicate_model_id = model_identifier
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        use_subject_token = self.replicate.config.profile_uses_subject_token(profile)
        subject_token = self._build_subject_token(project) if use_subject_token else None

        resolved_image_ids: List[str] = []
        training_run: Optional[TrainingRun] = None
        image_ids = [str(item) for item in (image_ids or []) if item]

        if image_ids:
            draft = self.training_run_repo.get_draft_by_project(project_id)
            if draft:
                training_run = self.training_run_repo.replace_images(draft.id, image_ids)
            else:
                training_run = self.training_run_repo.create(
                    project_id=project_id,
                    image_ids=image_ids,
                    status=TrainingRun.STATUS_PENDING,
                )
        else:
            draft = self.training_run_repo.get_draft_by_project(project_id)
            if not draft or not draft.image_ids:
                raise ValueError("No draft training images available")
            training_run = draft

        resolved_image_ids = training_run.image_ids or []
        if not resolved_image_ids:
            raise ValueError("At least one image ID is required")

        if training_run.status == TrainingRun.STATUS_DRAFT:
            training_run = self.training_run_repo.update_status(
                training_run.id,
                TrainingRun.STATUS_PENDING,
            )

        try:
            # Create ZIP of the specific training images
            zip_file_buffer = self.image_service.create_zip_from_images(resolved_image_ids)

            # Start training (config comes from YAML, with optional overrides)
            overrides = dict(config_override or {})
            if use_subject_token and subject_token:
                overrides.setdefault("token_string", subject_token)
                overrides.setdefault("trigger_word", subject_token)

            replicate_training_id = self.replicate.train(
                model_name=model_name,
                training_data=zip_file_buffer,
                config_override=overrides,
                profile=profile
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
            self.model_project_repo.update_status(
                project_id,
                ModelProject.STATUS_TRAINING,
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

    def delete_training_run(self, training_run_id: str) -> None:
        """
        Delete a training run and cancel it with Replicate if still running.
        """
        training_run = self.training_run_repo.get_by_id(training_run_id)

        if (
            training_run.replicate_training_id
            and training_run.status in (
                TrainingRun.STATUS_PENDING,
                TrainingRun.STATUS_STARTING,
                TrainingRun.STATUS_PROCESSING,
            )
        ):
            self.replicate.cancel_training(training_run.replicate_training_id)

        # Delete training images associated with this run
        for image_id in training_run.image_ids or []:
            try:
                self.image_service.delete_image(image_id)
            except Exception as exc:
                print(f"[TRAINING RUN DELETE] Failed to delete image {image_id}: {exc}")

        self.training_run_repo.delete(training_run_id)

    def _load_reference_images_from_ids(self, image_ids: List[str]) -> List[Any]:
        """Convert stored image IDs into binary streams for generation"""
        loaded_files: List[Any] = []
        for image_id in image_ids:
            try:
                image_meta = self.image_service.image_repo.get_image(image_id)
                file_bytes = self.image_service.download_image(image_id)
                if not file_bytes:
                    continue
                stream = BytesIO(file_bytes)
                # replicate.run expects file-like object with a name attribute
                stream.name = image_meta.filename or f"{image_id}.png"
                loaded_files.append(stream)
            except Exception as exc:
                print(f"[REFERENCE IMAGE LOAD] Failed to load {image_id}: {exc}")
        return loaded_files

    def generate(self,
                prompt: str,
                project_id: str,
                reference_images: Optional[List[Any]] = None,
                reference_image_ids: Optional[List[str]] = None,
                config_override: Optional[Dict[str, Any]] = None,
                include_subject_description: bool = True):
        """
        Generate an image using the model (trained or generation-only)

        Args:
            prompt: Text prompt for image generation
            project_id: Model project ID
            reference_images: Optional list of reference images (file-like objects)
                            Used for generation-only models that support reference images
            config_override: Optional dict to override specific config values from YAML
                           Example: {"aspect_ratio": "16:9", "guidance_scale": 4.0}

        Returns:
            GenerationHistory object with status and prediction ID
        """
        project = self.model_project_repo.get_project(project_id)
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        provider = project.get_provider()

        prompt_text = prompt.strip() if isinstance(prompt, str) else prompt
        prompt_with_description = prompt_text
        if include_subject_description and project.subject_description:
            desc = project.subject_description.strip()
            if desc:
                    prompt_with_description = f"{prompt_with_description}\n\nSubject description: {desc}" if prompt_with_description else desc

        resolved_reference_images: List[Any] = list(reference_images or [])
        if reference_image_ids:
            resolved_reference_images.extend(
                self._load_reference_images_from_ids(reference_image_ids)
            )

        resolved_reference_image_ids = [str(item) for item in (reference_image_ids or []) if item]

        # For generation-only models, use direct generation (no trained model needed)
        if not project.requires_training():
            # Route to the appropriate generation service based on provider
            if provider == "stability_ai":
                prediction_id = str(uuid.uuid4())
                return self._create_generation_history(
                    project_id=project_id,
                    prompt=prompt_text,
                    reference_image_ids=resolved_reference_image_ids,
                    include_subject_description=include_subject_description,
                    prediction_id=prediction_id,
                    provider="stability_ai",
                )
            else:
                # Use Replicate for generation-only models (e.g., flux_pro)
                # Use first reference image if provided (for models that support it like Flux Redux)
                image_prompt = resolved_reference_images[0] if resolved_reference_images else None
                prediction = self.replicate.create_prediction_with_model(
                    prompt=prompt_with_description,
                    profile=profile,
                    image_prompt=image_prompt,
                    config_override=config_override,
                )
                return self._create_generation_history(
                    project_id=project_id,
                    prompt=prompt_text,
                    reference_image_ids=resolved_reference_image_ids,
                    include_subject_description=include_subject_description,
                    prediction_id=prediction.id,
                    provider="replicate",
                )
        else:
            # For training models, use the trained model
            model_identifier = self.__get_model_identifier(project)
            use_subject_token = self.replicate.config.profile_uses_subject_token(profile)
            subject_token = self._build_subject_token(project) if use_subject_token else None
            prompt_to_use = prompt_with_description

            if use_subject_token and subject_token:
                if project.subject_name:
                    pattern = re.compile(re.escape(project.subject_name), re.IGNORECASE)
                    prompt_to_use = pattern.sub(subject_token, prompt_to_use)
                if subject_token.lower() not in prompt_to_use.lower():
                    prompt_to_use = f"{subject_token}, {prompt_to_use}".strip(", ")

            prediction = self.replicate.create_prediction(
                prompt=prompt_to_use,
                model_name=model_identifier,
                config_override=config_override,
                profile=profile,
            )
            return self._create_generation_history(
                project_id=project_id,
                prompt=prompt_text,
                reference_image_ids=resolved_reference_image_ids,
                include_subject_description=include_subject_description,
                prediction_id=prediction.id,
                provider="replicate",
            )

        image_data = BytesIO(image_bytes)
        file = FileStorage(image_data)
        image = self.image_service.save_image(project_id, file, "out.jpg", image_type="generated")

        return self._create_generation_history(
            project_id=project_id,
            prompt=prompt_text,
            reference_image_ids=resolved_reference_image_ids,
            include_subject_description=include_subject_description,
            image_ids=[image.id],
            status=GenerationHistory.STATUS_COMPLETED,
            provider=provider,
        )

    def _create_generation_history(
        self,
        project_id: str,
        prompt: str,
        reference_image_ids: Optional[List[str]] = None,
        include_subject_description: Optional[bool] = None,
        prediction_id: Optional[str] = None,
        provider: Optional[str] = None,
        image_ids: Optional[List[str]] = None,
        status: str = GenerationHistory.STATUS_PROCESSING,
    ) -> GenerationHistory:
        draft = self.generation_history_repo.get_draft_by_project(project_id)
        if draft:
            if status == GenerationHistory.STATUS_PROCESSING:
                return self.generation_history_repo.promote_draft_to_processing(
                    draft.id,
                    prompt,
                    reference_image_ids=reference_image_ids,
                    include_subject_description=include_subject_description,
                    prediction_id=prediction_id,
                    provider=provider,
                )
            return self.generation_history_repo.finalize_draft(
                draft.id,
                prompt,
                image_ids or [],
                reference_image_ids=reference_image_ids,
                include_subject_description=include_subject_description,
            )

        return self.generation_history_repo.create(
            project_id=project_id,
            prompt=prompt,
            image_ids=image_ids or [],
            reference_image_ids=reference_image_ids or [],
            status=status,
            include_subject_description=include_subject_description,
            prediction_id=prediction_id,
            provider=provider,
        )

    def update_generation_history_status(self, history_id: str) -> GenerationHistory:
        history = self.generation_history_repo.get_by_id(history_id)
        if history.status != GenerationHistory.STATUS_PROCESSING:
            return history

        if history.provider == "replicate" and history.prediction_id:
            prediction = self.replicate.get_prediction_details(history.prediction_id)
            status = prediction.get("status")
            error_message = prediction.get("error_message")

            if status in ("starting", "processing"):
                return history

            if status == "succeeded":
                if history.image_ids:
                    return self.generation_history_repo.update_status(
                        history.id,
                        GenerationHistory.STATUS_COMPLETED,
                        image_ids=history.image_ids,
                    )

                output_urls = prediction.get("output_urls") or []
                image_ids: List[str] = []
                for index, url in enumerate(output_urls):
                    response = requests.get(url, timeout=30)
                    if response.status_code != 200:
                        continue
                    image_data = BytesIO(response.content)
                    file = FileStorage(image_data)
                    filename = f"generated_{history.id}_{index + 1}.jpg"
                    image = self.image_service.save_image(
                        history.project_id,
                        file,
                        filename,
                        image_type="generated",
                    )
                    image_ids.append(image.id)

                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_COMPLETED,
                    image_ids=image_ids,
                )

            if status == "failed":
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_FAILED,
                    error_message=error_message,
                )

            if status == "canceled":
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_CANCELED,
                    error_message=error_message,
                )

        if history.provider == "stability_ai":
            try:
                if history.image_ids:
                    return self.generation_history_repo.update_status(
                        history.id,
                        GenerationHistory.STATUS_COMPLETED,
                        image_ids=history.image_ids,
                    )

                project = self.model_project_repo.get_project(history.project_id)
                prompt_with_description = self._build_prompt_with_description(
                    history.prompt,
                    project,
                    history.include_subject_description,
                )
                image_bytes = self._generate_stability_image_bytes(
                    project,
                    prompt_with_description,
                    history.reference_image_ids or [],
                )
                image_data = BytesIO(image_bytes)
                file = FileStorage(image_data)
                image = self.image_service.save_image(
                    history.project_id,
                    file,
                    f"generated_{history.id}_1.jpg",
                    image_type="generated",
                )
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_COMPLETED,
                    image_ids=[image.id],
                )
            except Exception as exc:
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_FAILED,
                    error_message=str(exc),
                )

        return history

    def _build_prompt_with_description(
        self,
        prompt: str,
        project: ModelProject,
        include_subject_description: Optional[bool],
    ) -> str:
        prompt_text = prompt.strip() if isinstance(prompt, str) else prompt
        if include_subject_description and project.subject_description:
            desc = project.subject_description.strip()
            if desc:
                return f"{prompt_text}\n\nSubject description: {desc}" if prompt_text else desc
        return prompt_text

    def _generate_stability_image_bytes(
        self,
        project: ModelProject,
        prompt_with_description: str,
        reference_image_ids: List[str],
    ) -> bytes:
        provider = "stability_ai"
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        gen_config = generation_models_config.get_generation_config(provider, profile)
        method = generation_models_config.get_method(provider, profile)

        prompt_to_use = generation_models_config.build_prompt(
            provider,
            profile,
            prompt_with_description,
        )
        negative_prompt = generation_models_config.get_negative_prompt_template(
            provider,
            profile,
        )

        resolved_reference_images = self._load_reference_images_from_ids(reference_image_ids)

        if method == "style_transfer":
            if not resolved_reference_images:
                raise ValueError("Style transfer requires at least one reference image")

            style_id = generation_models_config.get_style_reference_id(provider, profile)
            style_image = generation_models_config.get_style_image(style_id) if style_id else None
            if not style_image:
                raise ValueError(f"Style reference '{style_id}' not found")

            style_strength = gen_config.get('style_strength', 0.7)
            return self.stability.style_transfer(
                init_image=resolved_reference_images[0],
                style_image=style_image,
                prompt=prompt_to_use,
                style_strength=style_strength,
                negative_prompt=negative_prompt,
                output_format=gen_config.get('output_format', 'png'),
            )

        style_preset = generation_models_config.get_style_preset(provider, profile)
        image_strength = gen_config.get('image_strength', 0.35)
        init_image = resolved_reference_images[0] if resolved_reference_images else None

        result = self.stability.generate_image(
            prompt=prompt_to_use,
            negative_prompt=negative_prompt,
            style_preset=style_preset,
            init_image=init_image,
            image_strength=image_strength,
            width=gen_config.get('width', 1024),
            height=gen_config.get('height', 1024),
            steps=gen_config.get('steps', 30),
            cfg_scale=gen_config.get('cfg_scale', 7.0),
        )

        return self.stability.decode_base64_image(result['image_data']).read()

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
            if replicate_status == TrainingRun.STATUS_SUCCEEDED:
                self.model_project_repo.update_status(
                    training_run.project_id,
                    ModelProject.STATUS_READY,
                )

        return training_run
