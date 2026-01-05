from typing import Optional, Dict, Any, List

from src.models.generation_history import GenerationHistory
from src.models.model_project import ModelProject
from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.services.external.replicate_service import ReplicateService
from src.services.external.stability_service import StabilityService
from src.services.generation.replicate_generation_service import ReplicateGenerationService
from src.services.generation.stability_generation_service import StabilityGenerationService
from src.services.image_service import ImageService
from src.services.model_identity_service import ModelIdentityService
from src.services.prompt_service import PromptService


class ModelGenerationService:
    """Generation flow for model projects."""

    def __init__(
        self,
        image_service: ImageService,
        replicate: ReplicateService,
        stability: StabilityService,
        generation_history_repo: GenerationHistoryRepo,
        model_project_repo: ModelProjectRepo,
        identity_service: ModelIdentityService,
    ) -> None:
        self.model_project_repo = model_project_repo
        self.prompt_service = PromptService()
        self.replicate_generation = ReplicateGenerationService(
            image_service=image_service,
            replicate=replicate,
            generation_history_repo=generation_history_repo,
            model_project_repo=model_project_repo,
            identity_service=identity_service,
        )
        self.stability_generation = StabilityGenerationService(
            image_service=image_service,
            stability=stability,
            generation_history_repo=generation_history_repo,
            model_project_repo=model_project_repo,
        )

    def generate(
        self,
        prompt: str,
        project_id: str,
        reference_images: Optional[List[Any]] = None,
        reference_image_ids: Optional[List[str]] = None,
        config_override: Optional[Dict[str, Any]] = None,
        include_subject_description: bool = True,
    ) -> GenerationHistory:
        project = self.model_project_repo.get_project(project_id)
        prompt_text = prompt.strip() if isinstance(prompt, str) else prompt
        if project.get_provider() == "stability_ai":
            return self.stability_generation.start_generation(
                project=project,
                prompt_text=prompt_text,
                include_subject_description=include_subject_description,
                reference_image_ids=reference_image_ids or [],
            )

        return self.replicate_generation.start_generation(
            project=project,
            prompt_text=prompt_text,
            include_subject_description=include_subject_description,
            reference_images=reference_images,
            reference_image_ids=reference_image_ids,
            config_override=config_override,
        )

    def update_generation_history_status(self, history_id: str) -> GenerationHistory:
        history = self.replicate_generation.generation_history_repo.get_by_id(history_id)
        if history.status != GenerationHistory.STATUS_PROCESSING:
            return history

        if history.provider == "stability_ai":
            return self.stability_generation.update_generation_status(history)

        if history.provider == "replicate":
            return self.replicate_generation.update_generation_status(history)

        return history

    
