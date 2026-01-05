from typing import Optional, List, Any
from io import BytesIO
import uuid

from werkzeug.datastructures import FileStorage

from src.models.generation_history import GenerationHistory
from src.models.model_project import ModelProject
from src.repositories.db.generation_history_repo import GenerationHistoryRepo
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.services.external.stability_service import StabilityService
from src.services.image_service import ImageService
from src.services.prompt_service import PromptService
from src.utils.config.generation_models_config import generation_models_config


class StabilityGenerationService:
    """Stability-specific generation logic."""

    def __init__(
        self,
        image_service: ImageService,
        stability: StabilityService,
        generation_history_repo: GenerationHistoryRepo,
        model_project_repo: ModelProjectRepo,
    ) -> None:
        self.image_service = image_service
        self.stability = stability
        self.generation_history_repo = generation_history_repo
        self.model_project_repo = model_project_repo
        self.prompt_service = PromptService()

    def start_generation(
        self,
        project: ModelProject,
        prompt_text: str,
        include_subject_description: bool,
        reference_image_ids: Optional[List[str]],
    ) -> GenerationHistory:
        prediction_id = self._build_prediction_id()
        draft = self.generation_history_repo.get_or_create_draft(project.id)
        return self.generation_history_repo.promote_draft_to_processing(
            draft.id,
            prompt_text,
            reference_image_ids=reference_image_ids or [],
            include_subject_description=include_subject_description,
            prediction_id=prediction_id,
            provider="stability_ai",
        )

    def update_generation_status(self, history: GenerationHistory) -> GenerationHistory:
        if history.provider != "stability_ai":
            return history

        try:
            if history.image_ids:
                return self.generation_history_repo.update_status(
                    history.id,
                    GenerationHistory.STATUS_COMPLETED,
                    image_ids=history.image_ids,
                )

            project = self.model_project_repo.get_project(history.project_id)
            prompt_with_description = self.prompt_service.build_with_subject_description(
                history.prompt,
                project,
                history.include_subject_description,
            )
            image_bytes = self._generate_image_bytes(
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

    def _generate_image_bytes(
        self,
        project: ModelProject,
        prompt_with_description: str,
        reference_image_ids: List[str],
    ) -> bytes:
        provider = "stability_ai"
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        gen_config = generation_models_config.get_generation_config(provider, profile)
        method = generation_models_config.get_method(provider, profile)

        prompt_to_use = self.prompt_service.build_provider_prompt(
            provider,
            profile,
            prompt_with_description,
        )
        negative_prompt = self.prompt_service.get_negative_prompt(provider, profile)

        resolved_reference_images = self._load_reference_images_from_ids(reference_image_ids)

        if method == "style_transfer":
            if not resolved_reference_images:
                raise ValueError("Style transfer requires at least one reference image")

            style_id = generation_models_config.get_style_reference_id(provider, profile)
            style_image = generation_models_config.get_style_image(style_id) if style_id else None
            if not style_image:
                raise ValueError(f"Style reference '{style_id}' not found")

            style_strength = gen_config.get("style_strength", 0.7)
            return self.stability.style_transfer(
                init_image=resolved_reference_images[0],
                style_image=style_image,
                prompt=prompt_to_use,
                style_strength=style_strength,
                negative_prompt=negative_prompt,
                output_format=gen_config.get("output_format", "png"),
            )

        style_preset = generation_models_config.get_style_preset(provider, profile)
        image_strength = gen_config.get("image_strength", 0.35)
        init_image = resolved_reference_images[0] if resolved_reference_images else None

        result = self.stability.generate_image(
            prompt=prompt_to_use,
            negative_prompt=negative_prompt,
            style_preset=style_preset,
            init_image=init_image,
            image_strength=image_strength,
            width=gen_config.get("width", 1024),
            height=gen_config.get("height", 1024),
            steps=gen_config.get("steps", 30),
            cfg_scale=gen_config.get("cfg_scale", 7.0),
        )

        return self.stability.decode_base64_image(result["image_data"]).read()

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
        # Simple unique ID to track async status for non-Replicate providers.
        return str(uuid.uuid4())
