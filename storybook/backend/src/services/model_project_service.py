from typing import List
from flask import request

from src.data.model_project_repo import ModelProjectRepo
from src.data.image_repo import ImageRepo
from src.data.generation_history_repo import GenerationHistoryRepo
from src.data.training_run_repo import TrainingRunRepo
from src.models.model_project import ModelProject
from src.proxies.replicate_service import ReplicateService

class ModelProjectService:
    def __init__(self):
        self.model_project_repo = ModelProjectRepo()
        self.image_repo = ImageRepo()
        self.generation_history_repo = GenerationHistoryRepo()
        self.training_run_repo = TrainingRunRepo()
        self.replicate_service = ReplicateService()

    def get_projects(self) -> List[ModelProject]:
        # Retrieve all model projects from the repo
        return self.model_project_repo.get_projects()

    def get_project(self, project_id: str) -> ModelProject:
        # Retrieve a specific model project by ID from the repo
        return self.model_project_repo.get_project(project_id)

    def create_project(self, name: str, subject_name: str, model_type: str, subject_description: str = None) -> ModelProject:
        # Create a new model project in the repo
        if model_type not in ModelProject.VALID_MODEL_TYPES:
            raise ValueError(f"Invalid model type: {model_type}")
        return self.model_project_repo.create_project(name, subject_name, model_type, subject_description)

    def update_project(self, project_id: str, name: str = None, subject_name: str = None, model_type: str = None, subject_description: str = None) -> ModelProject:
        # Update a model project's metadata
        if model_type and model_type not in ModelProject.VALID_MODEL_TYPES:
            raise ValueError(f"Invalid model type: {model_type}")
        return self.model_project_repo.update_project(project_id, name, subject_name, model_type, subject_description=subject_description)

    def update_status(self, project_id: str, status: str) -> ModelProject:
        # Update a model project's status
        return self.model_project_repo.update_status(project_id, status)

    def delete_project(self, project_id: str) -> None:
        """
        Delete a project and all associated data:
        - Training runs (all historical training sessions)
        - Generation history entries
        - All images (from S3 and MongoDB)
        - Replicate model (if exists)
        - Project metadata

        Args:
            project_id: UUID of the project to delete

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        user_id = request.cognito_claims['sub']
        project = self.model_project_repo.get_project(project_id)

        # 1. Delete all training runs for this project
        try:
            self.training_run_repo.delete_by_project(project_id)
        except Exception as e:
            print(f"Error deleting training runs: {e}")

        # 2. Delete all generation history for this project
        try:
            self.generation_history_repo.delete_by_project(project_id)
        except Exception as e:
            print(f"Error deleting generation history for project {project_id}: {e}")

        # 3. Delete all images for this project (S3 + MongoDB, including reference images)
        try:
            self.image_repo.delete_project_images(project_id)
        except Exception as e:
            print(f"Error deleting images for project {project_id}: {e}")

        # 4. Delete Replicate model if it exists
        model_identifier = project.replicate_model_id
        try:
            if self.replicate_service.model_exists(model_identifier):
                self.replicate_service.delete_model(model_identifier)
        except Exception as e:
            print(f"Error deleting Replicate model {model_identifier}: {e}")

        # 5. Finally, delete the project itself
        self.model_project_repo.delete_project(project_id)
