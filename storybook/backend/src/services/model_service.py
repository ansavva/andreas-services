"""
Model Service - Facade for training and generation workflows.
"""
from typing import Optional, Dict, Any, List

from src.models.generation_history import GenerationHistory
from src.models.training_run import TrainingRun
from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.repositories.db.training_run_repo import TrainingRunRepo
from src.services.external.replicate_service import ReplicateService
from src.services.external.stability_service import StabilityService
from src.services.image_service import ImageService
from src.services.model_generation_service import ModelGenerationService
from src.services.model_identity_service import ModelIdentityService
from src.services.model_training_service import ModelTrainingService


class ModelService:
    """Facade for managing AI model training and image generation."""

    def __init__(self) -> None:
        image_service = ImageService()
        replicate = ReplicateService()
        stability = StabilityService()
        training_run_repo = TrainingRunRepo()
        model_project_repo = ModelProjectRepo()
        generation_history_repo = GenerationHistoryRepo()

        identity_service = ModelIdentityService(
            replicate=replicate,
            model_project_repo=model_project_repo,
        )

        self._replicate = replicate
        self._identity = identity_service
        self._training = ModelTrainingService(
            image_service=image_service,
            replicate=replicate,
            training_run_repo=training_run_repo,
            model_project_repo=model_project_repo,
            identity_service=identity_service,
        )
        self._generation = ModelGenerationService(
            image_service=image_service,
            replicate=replicate,
            stability=stability,
            generation_history_repo=generation_history_repo,
            model_project_repo=model_project_repo,
            identity_service=identity_service,
        )

    def ready(self, project_id: str) -> bool:
        return self._identity.ready(project_id)

    def train(
        self,
        project_id: str,
        image_ids: Optional[List[str]] = None,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> TrainingRun:
        return self._training.train(
            project_id=project_id,
            image_ids=image_ids,
            config_override=config_override,
        )

    def check_training_status(self, training_id: str) -> str:
        return self._training.check_training_status(training_id)

    def delete_training_run(self, training_run_id: str) -> None:
        self._training.delete_training_run(training_run_id)

    def get_training_runs(self, project_id: str) -> List[TrainingRun]:
        return self._training.get_training_runs(project_id)

    def update_training_run_status(self, training_run_id: str) -> TrainingRun:
        return self._training.update_training_run_status(training_run_id)

    def generate(
        self,
        prompt: str,
        project_id: str,
        reference_images: Optional[List[Any]] = None,
        reference_image_ids: Optional[List[str]] = None,
        config_override: Optional[Dict[str, Any]] = None,
        include_subject_description: bool = True,
    ) -> GenerationHistory:
        return self._generation.generate(
            prompt=prompt,
            project_id=project_id,
            reference_images=reference_images,
            reference_image_ids=reference_image_ids,
            config_override=config_override,
            include_subject_description=include_subject_description,
        )

    def update_generation_history_status(self, history_id: str) -> GenerationHistory:
        return self._generation.update_generation_history_status(history_id)

    def cancel_training(self, training_id: str) -> bool:
        return self._replicate.cancel_training(training_id)
