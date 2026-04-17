from typing import Optional, List, Any
from io import BytesIO
import uuid

from PIL import Image
from werkzeug.datastructures import FileStorage

from src.models.generation_history import GenerationHistory
from src.models.model_project import ModelProject
from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.services.external.gemini_service import GeminiService
from src.services.image_service import ImageService
from src.services.prompt_service import PromptService
from src.utils.config.generation_models_config import generation_models_config


class GeminiGenerationService:
    """Gemini-specific generation logic."""

    def __init__(
        self,
        image_service: ImageService,
        gemini: GeminiService,
        generation_history_repo: GenerationHistoryRepo,
        model_project_repo: ModelProjectRepo,
    ) -> None:
        self.image_service = image_service
        self.gemini = gemini
        self.generation_history_repo = generation_history_repo
        self.model_project_repo = model_project_repo
        self.prompt_service = PromptService()

    def start_generation(
        self,
        project: ModelProject,
        prompt_text: str,
        include_subject_description: bool,
        reference_images: Optional[List[Any]],
        reference_image_ids: Optional[List[str]],
    ) -> GenerationHistory:
        prediction_id = self._build_prediction_id()
        draft = self.generation_history_repo.get_or_create_draft(project.id)
        history = self.generation_history_repo.promote_draft_to_processing(
            draft.id,
            prompt_text,
            reference_image_ids=reference_image_ids or [],
            include_subject_description=include_subject_description,
            prediction_id=prediction_id,
            provider="gemini",
        )

        # If reference images were provided directly, generate immediately.
        if reference_images:
            try:
                image_ids = self._generate_and_store(
                    project=project,
                    prompt_text=prompt_text,
                    include_subject_description=include_subject_description,
                    reference_images=reference_images,
                )
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_COMPLETED,
                    image_ids=image_ids,
                )
            except Exception as exc:
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_FAILED,
                    error_message=str(exc),
                )

        return history

    def update_generation_status(self, history: GenerationHistory) -> GenerationHistory:
        if history.provider != "gemini":
            return history

        if history.image_ids:
            return self.generation_history_repo.update_status(
                history.id,
                GenerationHistory.STATUS_COMPLETED,
                image_ids=history.image_ids,
            )

        try:
            project = self.model_project_repo.get_project(history.project_id)
            image_ids = self._generate_and_store(
                project=project,
                prompt_text=history.prompt,
                include_subject_description=history.include_subject_description,
                reference_images=self._load_reference_images_from_ids(
                    history.reference_image_ids or []
                ),
            )
            return self.generation_history_repo.update_status(
                history.id,
                GenerationHistory.STATUS_COMPLETED,
                image_ids=image_ids,
            )
        except Exception as exc:
            return self.generation_history_repo.update_status(
                history.id,
                GenerationHistory.STATUS_FAILED,
                error_message=str(exc),
            )

    def _generate_and_store(
        self,
        project: ModelProject,
        prompt_text: str,
        include_subject_description: bool,
        reference_images: List[Any],
    ) -> List[str]:
        provider = "gemini"
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        prompt_with_description = self.prompt_service.build_with_subject_description(
            prompt_text,
            project,
            include_subject_description,
        )
        prompt_to_use = self.prompt_service.build_provider_prompt(
            provider,
            profile,
            prompt_with_description,
        )

        image_bytes_list = self.gemini.generate_images(
            prompt=prompt_to_use,
            profile=profile,
            reference_images=self._normalize_reference_images(reference_images),
        )

        image_ids: List[str] = []
        for index, image_bytes in enumerate(image_bytes_list):
            file = FileStorage(BytesIO(image_bytes))
            filename = f"generated_{project.id}_{uuid.uuid4().hex}_{index + 1}.png"
            image = self.image_service.save_image(
                project.id,
                file,
                filename,
                image_type="generated",
            )
            image_ids.append(image.id)

        if not image_ids:
            raise RuntimeError("Gemini returned no images to store.")

        return image_ids

    def _normalize_reference_images(self, reference_images: List[Any]) -> List[Image.Image]:
        normalized: List[Image.Image] = []
        for image in reference_images:
            if isinstance(image, Image.Image):
                normalized.append(image)
                continue
            stream = getattr(image, "stream", None)
            if stream is not None:
                stream.seek(0)
                normalized.append(Image.open(stream))
                continue
            if hasattr(image, "seek"):
                image.seek(0)
                normalized.append(Image.open(image))
                continue
        return normalized

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

    def _build_prediction_id(self) -> str:
        return str(uuid.uuid4())
