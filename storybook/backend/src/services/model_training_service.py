from typing import Optional, Dict, Any, List

from src.models.model_project import ModelProject
from src.models.training_run import TrainingRun
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.repositories.db.training_run_repo import TrainingRunRepo
from src.services.image_service import ImageService
from src.services.external.replicate_service import ReplicateService
from src.services.model_identity_service import ModelIdentityService


class ModelTrainingService:
    """Training flow for model projects."""

    def __init__(
        self,
        image_service: ImageService,
        replicate: ReplicateService,
        training_run_repo: TrainingRunRepo,
        model_project_repo: ModelProjectRepo,
        identity_service: ModelIdentityService,
    ) -> None:
        self.image_service = image_service
        self.replicate = replicate
        self.training_run_repo = training_run_repo
        self.model_project_repo = model_project_repo
        self.identity_service = identity_service

    def train(
        self,
        project_id: str,
        image_ids: Optional[List[str]] = None,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> TrainingRun:
        project = self.model_project_repo.get_project(project_id)
        model_name = self.identity_service.get_model_name(project)
        model_identifier = f"{self.replicate.owner}/{model_name}"
        if project.replicate_model_id != model_identifier:
            self.model_project_repo.update_project(
                project_id,
                replicate_model_id=model_identifier,
            )
            project.replicate_model_id = model_identifier

        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        use_subject_token = self.replicate.config.profile_uses_subject_token(profile)
        subject_token = (
            self.identity_service.build_subject_token(project) if use_subject_token else None
        )

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
            zip_file_buffer = self.image_service.create_zip_from_images(resolved_image_ids)

            overrides = dict(config_override or {})
            if use_subject_token and subject_token:
                overrides.setdefault("token_string", subject_token)
                overrides.setdefault("trigger_word", subject_token)

            replicate_training_id = self.replicate.train(
                model_name=model_name,
                training_data=zip_file_buffer,
                config_override=overrides,
                profile=profile,
            )

            training_run = self.training_run_repo.set_replicate_id(
                training_run.id,
                replicate_training_id,
            )
            training_run = self.training_run_repo.update_status(
                training_run.id,
                TrainingRun.STATUS_STARTING,
            )
            self.model_project_repo.update_status(
                project_id,
                ModelProject.STATUS_TRAINING,
            )
        except Exception as exc:
            self.training_run_repo.update_status(
                training_run.id,
                TrainingRun.STATUS_FAILED,
                error_message=str(exc),
            )
            raise

        return training_run

    def check_training_status(self, training_id: str) -> str:
        return self.replicate.get_training_status(training_id)

    def delete_training_run(self, training_run_id: str) -> None:
        training_run = self.training_run_repo.get_by_id(training_run_id)

        if (
            training_run.replicate_training_id
            and training_run.status
            in (
                TrainingRun.STATUS_PENDING,
                TrainingRun.STATUS_STARTING,
                TrainingRun.STATUS_PROCESSING,
            )
        ):
            self.replicate.cancel_training(training_run.replicate_training_id)

        for image_id in training_run.image_ids or []:
            try:
                self.image_service.delete_image(image_id)
            except Exception as exc:
                print(f"[TRAINING RUN DELETE] Failed to delete image {image_id}: {exc}")

        self.training_run_repo.delete(training_run_id)

    def get_training_runs(self, project_id: str) -> List[TrainingRun]:
        return self.training_run_repo.list_by_project(project_id)

    def update_training_run_status(self, training_run_id: str) -> TrainingRun:
        training_run = self.training_run_repo.get_by_id(training_run_id)

        if not training_run.replicate_training_id:
            return training_run

        replicate_info = self.replicate.get_training_status_details(
            training_run.replicate_training_id
        )
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
                error_message if replicate_status == TrainingRun.STATUS_FAILED else None,
            )
            if replicate_status == TrainingRun.STATUS_SUCCEEDED:
                self.model_project_repo.update_status(
                    training_run.project_id,
                    ModelProject.STATUS_READY,
                )

        return training_run
