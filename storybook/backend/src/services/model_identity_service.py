from typing import Optional
from flask import request

from src.models.model_project import ModelProject
from src.repositories.db.model_project_repo import ModelProjectRepo
from src.services.external.replicate_service import ReplicateService


class ModelIdentityService:
    """Model naming and readiness checks."""

    def __init__(
        self,
        replicate: ReplicateService,
        model_project_repo: ModelProjectRepo,
    ) -> None:
        self.replicate = replicate
        self.model_project_repo = model_project_repo

    def get_model_name(self, project: ModelProject) -> str:
        """Generate model name based on user ID, project ID, and model profile."""
        user_id = request.cognito_claims["sub"]
        profile = project.model_type or ModelProject.DEFAULT_MODEL_TYPE
        return self.replicate.config.build_model_name(profile, user_id, project.id)

    def get_model_identifier(self, project: ModelProject) -> str:
        """Return the stored owner/model identifier or fallback to short name."""
        if project.replicate_model_id:
            return project.replicate_model_id
        return self.get_model_name(project)

    def build_subject_token(self, project: ModelProject) -> str:
        """Generate a consistent token string based on subject name."""
        subject = (project.subject_name or "subject").lower()
        sanitized = "".join(ch if ch.isalnum() else "_" for ch in subject).strip("_")
        if not sanitized:
            sanitized = "subject"
        return f"{sanitized}_tok"

    def ready(self, project_id: str) -> bool:
        """
        Check if a trained model is ready for this project.

        For generation-only models, always returns True.
        """
        project = self.model_project_repo.get_project(project_id)

        if not project.requires_training():
            return True

        if project.status != ModelProject.STATUS_READY:
            return False

        model_identifier = self.get_model_identifier(project)
        return self.replicate.model_exists(model_identifier)
