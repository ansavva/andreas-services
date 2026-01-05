from typing import Optional, Dict, Any, List
from io import BytesIO

import requests
from werkzeug.datastructures import FileStorage

from src.models.generation_history import GenerationHistory
from src.models.model_project import ModelProject
from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.services.external.replicate_service import ReplicateService
from src.services.image_service import ImageService
from src.services.model_identity_service import ModelIdentityService
from src.services.prompt_service import PromptService


class ReplicateGenerationService:
    """Replicate-specific generation logic."""

    def __init__(
        self,
        image_service: ImageService,
        replicate: ReplicateService,
        generation_history_repo: GenerationHistoryRepo,
        model_project_repo: ModelProjectRepo,
        identity_service: ModelIdentityService,
    ) -> None:
        self.image_service = image_service
        self.replicate = replicate
        self.generation_history_repo = generation_history_repo
        self.model_project_repo = model_project_repo
        self.identity_service = identity_service
        self.prompt_service = PromptService()

    def _load_reference_images_from_ids(self, image_ids: List[str]) -> List[Any]:
        loaded_files: List[Any] = []
        for image_id in image_ids:
            try:
                image_meta = self.image_service.image_repo.get_image(image_id)
                file_bytes = self.image_service.download_image(image_id)
                if not file_bytes:
                    continue
                stream = BytesIO(file_bytes)
                stream.name = image_meta.filename or f"{image_id}.png"
                loaded_files.append(stream)
            except Exception as exc:
                print(f"[REFERENCE IMAGE LOAD] Failed to load {image_id}: {exc}")
        return loaded_files

    def start_generation(
        self,
        project: ModelProject,
        prompt_text: str,
        include_subject_description: bool,
        reference_images: Optional[List[Any]],
        reference_image_ids: Optional[List[str]],
        config_override: Optional[Dict[str, Any]],
    ) -> GenerationHistory:
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        prompt_with_description = self.prompt_service.build_with_subject_description(
            prompt_text,
            project,
            include_subject_description,
        )
        resolved_reference_images: List[Any] = list(reference_images or [])
        if reference_image_ids:
            resolved_reference_images.extend(
                self._load_reference_images_from_ids(reference_image_ids)
            )
        resolved_reference_image_ids = [
            str(item) for item in (reference_image_ids or []) if item
        ]

        if not project.requires_training():
            image_prompt = resolved_reference_images[0] if resolved_reference_images else None
            prediction = self.replicate.create_prediction_with_model(
                prompt=prompt_with_description,
                profile=profile,
                image_prompt=image_prompt,
                config_override=config_override,
            )
            return self.generation_history_repo.promote_draft_to_processing(
                self._resolve_draft_id(project.id),
                prompt_text,
                reference_image_ids=resolved_reference_image_ids,
                include_subject_description=include_subject_description,
                prediction_id=prediction.id,
                provider="replicate",
            )

        model_identifier = self.identity_service.get_model_identifier(project)
        use_subject_token = self.replicate.config.profile_uses_subject_token(profile)
        subject_token = (
            self.identity_service.build_subject_token(project) if use_subject_token else None
        )
        prompt_to_use = self.prompt_service.apply_subject_token(
            prompt_with_description,
            project.subject_name,
            subject_token,
        )

        prediction = self.replicate.create_prediction(
            prompt=prompt_to_use,
            model_name=model_identifier,
            config_override=config_override,
            profile=profile,
        )

        return self.generation_history_repo.promote_draft_to_processing(
            self._resolve_draft_id(project.id),
            prompt_text,
            reference_image_ids=resolved_reference_image_ids,
            include_subject_description=include_subject_description,
            prediction_id=prediction.id,
            provider="replicate",
        )

    def update_generation_status(self, history: GenerationHistory) -> GenerationHistory:
        if history.provider != "replicate" or not history.prediction_id:
            return history

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
            if not output_urls:
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_FAILED,
                    error_message="Replicate returned no outputs for this prediction.",
                )

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

            if not image_ids:
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_FAILED,
                    error_message="Failed to download generated images from Replicate.",
                )

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

        return history

    def _resolve_draft_id(self, project_id: str) -> str:
        draft = self.generation_history_repo.get_or_create_draft(project_id)
        return draft.id
