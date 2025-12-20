from typing import List

from src.data.model_project_repo import ModelProjectRepo
from src.models.model_project import ModelProject

class ModelProjectService:
    def __init__(self):
        self.model_project_repo = ModelProjectRepo()

    def get_projects(self) -> List[ModelProject]:
        # Retrieve all model projects from the repo
        return self.model_project_repo.get_projects()

    def get_project(self, project_id: str) -> ModelProject:
        # Retrieve a specific model project by ID from the repo
        return self.model_project_repo.get_project(project_id)

    def create_project(self, name: str, subject_name: str) -> ModelProject:
        # Create a new model project in the repo
        return self.model_project_repo.create_project(name, subject_name)

    def update_project(self, project_id: str, name: str = None, subject_name: str = None) -> ModelProject:
        # Update a model project's metadata
        return self.model_project_repo.update_project(project_id, name, subject_name)

    def update_status(self, project_id: str, status: str) -> ModelProject:
        # Update a model project's status
        return self.model_project_repo.update_status(project_id, status)