from typing import List

from src.data.project_repo import ProjectRepo
from src.models.project import Project

class ProjectService:
    def __init__(self):
        self.project_repo = ProjectRepo()
    
    def get_projects(self) -> List[Project]:
        # Retrieve all projects from the ImageRepo
        return self.project_repo.get_projects()

    def get_project(self, project_id: str) -> Project:
        # Retrieve a specific project by ID from the ImageRepo
        return self.project_repo.get_project(project_id)

    def create_project(self, name: str, subject_name: str) -> Project:
        # Create a new project in the ImageRepo
        return self.project_repo.create_project(name, subject_name)