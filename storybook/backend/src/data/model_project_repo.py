from typing import List
from flask import request
import uuid
from datetime import datetime

from src.data.database import get_db
from src.models.model_project import ModelProject

class ModelProjectRepo:
    """
    Project repository - handles CRUD operations for projects using MongoDB
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    def get_project(self, project_id: str) -> ModelProject:
        """
        Get a single project by ID for the current user

        Args:
            project_id: UUID of the project

        Returns:
            Project object

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        project_data = db.model_projects.find_one({
            '_id': project_id,
            'user_id': user_id
        })

        if not project_data:
            raise ValueError(f"Project with ID {project_id} not found.")

        return ModelProject.from_dict(project_data)

    def get_projects(self) -> List[ModelProject]:
        """
        Get all projects for the current user

        Returns:
            List of Project objects
        """
        db = get_db()
        user_id = self._get_user_id()

        projects_data = db.model_projects.find({
            'user_id': user_id
        }).sort('created_at', -1)  # Most recent first

        return [ModelProject.from_dict(p) for p in projects_data]

    def create_project(self, name: str, subject_name: str, model_type: str = None, subject_description: str = None) -> ModelProject:
        """
        Create a new project for the current user

        Args:
            name: Name of the project
            subject_name: Name of the subject (person, object, etc.)

        Returns:
            Created Project object
        """
        db = get_db()
        user_id = self._get_user_id()

        project_id = str(uuid.uuid4())
        project = ModelProject(
            id=project_id,
            name=name,
            subject_name=subject_name,
            subject_description=subject_description,
            user_id=user_id,
            status="DRAFT",
            model_type=model_type or ModelProject.DEFAULT_MODEL_TYPE,
            replicate_model_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.model_projects.insert_one(project.to_dict())

        return project

    def update_project(
        self,
        project_id: str,
        name: str = None,
        subject_name: str = None,
        model_type: str = None,
        replicate_model_id: str = None,
        subject_description: str = None
    ) -> ModelProject:
        """
        Update a project's name or subject_name

        Args:
            project_id: UUID of the project
            name: New name (optional)
            subject_name: New subject name (optional)

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        update_fields = {'updated_at': datetime.utcnow()}
        if name is not None:
            update_fields['name'] = name
        if subject_name is not None:
            update_fields['subject_name'] = subject_name
        if subject_description is not None:
            update_fields['subject_description'] = subject_description
        if model_type is not None:
            update_fields['model_type'] = model_type
        if replicate_model_id is not None:
            update_fields['replicate_model_id'] = replicate_model_id

        result = db.model_projects.update_one(
            {'_id': project_id, 'user_id': user_id},
            {'$set': update_fields}
        )

        if result.matched_count == 0:
            raise ValueError(f"Project with ID {project_id} not found.")

        return self.get_project(project_id)

    def update_status(self, project_id: str, status: str) -> ModelProject:
        """
        Update a project's status

        Args:
            project_id: UUID of the project
            status: New status (must be valid status from ModelProject.VALID_STATUSES)

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found, doesn't belong to user, or invalid status
        """
        if status not in ModelProject.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {ModelProject.VALID_STATUSES}")

        db = get_db()
        user_id = self._get_user_id()

        result = db.model_projects.update_one(
            {'_id': project_id, 'user_id': user_id},
            {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
        )

        if result.matched_count == 0:
            raise ValueError(f"Project with ID {project_id} not found.")

        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        """
        Delete a project (metadata only - S3 cleanup should be handled separately)

        Args:
            project_id: UUID of the project

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        db = get_db()
        user_id = self._get_user_id()

        result = db.model_projects.delete_one({
            '_id': project_id,
            'user_id': user_id
        })

        if result.deleted_count == 0:
            raise ValueError(f"Project with ID {project_id} not found.")

        # Note: Also delete associated images from MongoDB
        db.images.delete_many({'project_id': project_id})
