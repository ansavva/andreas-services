from typing import List
from flask import request
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.model_project import ModelProject


class ModelProjectRepo:
    """
    ModelProject repository - handles CRUD operations for model projects using DynamoDB.
    Table: STORYBOOK_MODEL_PROJECTS_TABLE  PK: project_id (S)
    GSI: user_id-created_at-index  PK: user_id (S), SK: created_at (S)
    """

    def __init__(self):
        pass

    def _get_user_id(self) -> str:
        """Get current user ID from Cognito claims"""
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_MODEL_PROJECTS_TABLE')

    def get_project(self, project_id: str) -> ModelProject:
        """
        Get a single project by ID for the current user.

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        user_id = self._get_user_id()
        resp = self._table().get_item(Key={'project_id': project_id})
        item = resp.get('Item')

        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Project with ID {project_id} not found.")

        return ModelProject.from_dict(item)

    def get_projects(self) -> List[ModelProject]:
        """Get all projects for the current user, most recent first."""
        user_id = self._get_user_id()

        resp = self._table().query(
            IndexName='user_id-created_at-index',
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False,
        )

        return [ModelProject.from_dict(p) for p in resp.get('Items', [])]

    def create_project(self, name: str, subject_name: str,
                       model_type: str = None,
                       subject_description: str = None) -> ModelProject:
        """Create a new project for the current user."""
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._table().put_item(Item=project.to_dict())
        return project

    def update_project(
        self,
        project_id: str,
        name: str = None,
        subject_name: str = None,
        model_type: str = None,
        replicate_model_id: str = None,
        subject_description: str = None,
    ) -> ModelProject:
        """
        Update a project's fields.

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        # Validates ownership
        self.get_project(project_id)

        now = datetime.now(timezone.utc).isoformat()
        set_parts = ['updated_at = :updated_at']
        expr_values = {':updated_at': now}
        expr_names = {}

        if name is not None:
            set_parts.append('#name = :name')
            expr_values[':name'] = name
            expr_names['#name'] = 'name'
        if subject_name is not None:
            set_parts.append('subject_name = :subject_name')
            expr_values[':subject_name'] = subject_name
        if subject_description is not None:
            set_parts.append('subject_description = :subject_description')
            expr_values[':subject_description'] = subject_description
        if model_type is not None:
            set_parts.append('model_type = :model_type')
            expr_values[':model_type'] = model_type
        if replicate_model_id is not None:
            set_parts.append('replicate_model_id = :replicate_model_id')
            expr_values[':replicate_model_id'] = replicate_model_id

        kwargs = dict(
            Key={'project_id': project_id},
            UpdateExpression='SET ' + ', '.join(set_parts),
            ExpressionAttributeValues=expr_values,
        )
        if expr_names:
            kwargs['ExpressionAttributeNames'] = expr_names

        self._table().update_item(**kwargs)
        return self.get_project(project_id)

    def update_status(self, project_id: str, status: str) -> ModelProject:
        """
        Update a project's status.

        Raises:
            ValueError: If project not found, doesn't belong to user, or invalid status
        """
        if status not in ModelProject.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {ModelProject.VALID_STATUSES}")

        # Validates ownership
        self.get_project(project_id)

        now = datetime.now(timezone.utc).isoformat()
        self._table().update_item(
            Key={'project_id': project_id},
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': status, ':updated_at': now},
        )

        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        """
        Delete a project (metadata only - S3 cleanup handled separately).
        Also deletes associated image records.

        Raises:
            ValueError: If project not found or doesn't belong to user
        """
        # Validates ownership
        self.get_project(project_id)
        self._table().delete_item(Key={'project_id': project_id})

        # Delete associated image records
        from src.repositories.db.story_project_repo import _delete_by_project_gsi
        _delete_by_project_gsi(
            _table('STORYBOOK_IMAGES_TABLE'),
            'project_id-created_at-index', 'project_id', project_id, 'image_id'
        )
