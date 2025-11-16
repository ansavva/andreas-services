from typing import List
from authlib.integrations.flask_oauth2 import current_token
from werkzeug.datastructures import FileStorage
import uuid

from src.data.s3_repo import S3Repo
from src.models.project import Project

class ProjectRepo:
    def __init__(self):
        self.s3_repo = S3Repo()
    
    def __create_directory(self):
        user_id = current_token.sub.split('|')[1]
        return f"users/{user_id}/projects"

    def extract_project_info(self, project_key: str, directory: str) -> Project:
        # Remove the directory portion of the key to isolate the project string
        project_key = project_key.replace(directory + "/", "").split('/')[0]  # Remove directory part from the project key
        project_id, project_name, subject_name = project_key.split("__ai__")
        return Project(id=project_id, name=project_name, subjectName=subject_name, key=project_key)

    def get_project(self, project_id: str) -> Project:
        directory = self.__create_directory()
        projects = self.s3_repo.list_files(directory, False)
        for project in projects:
            if "__ai__" in project:
                project = self.extract_project_info(project, directory)
                if project.id == project_id:
                    return project
        raise ValueError(f"Project with ID {project_id} not found.")    

    def get_projects(self) -> List[Project]:
        directory = self.__create_directory()
        projects = self.s3_repo.list_files(directory, False)
        formatted_projects = []
        for project in projects:
            if "__ai__" in project:
                project = self.extract_project_info(project, directory)
                formatted_projects.append(project)                
        return formatted_projects

    def create_project(self, name: str, subject_name: str) -> Project:
        project_guid = str(uuid.uuid4())
        directory = self.__create_directory()
        key = f"{directory}/{project_guid}__ai__{name}__ai__{subject_name}"
        self.s3_repo.create_directory(key)
        return Project(id=project_guid, name=name, subjectName=subject_name, key=key)