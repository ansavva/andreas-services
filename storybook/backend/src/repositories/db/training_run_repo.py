from typing import List, Optional
from flask import request
import uuid
from datetime import datetime

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.training_run import TrainingRun


class TrainingRunRepo:
    """
    Training Run repository.
    Table: STORYBOOK_TRAINING_RUNS_TABLE  PK: training_run_id (S)
    GSI:   project_id-created_at-index  PK: project_id (S), SK: created_at (S)
    """

    def _get_user_id(self) -> str:
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_TRAINING_RUNS_TABLE')

    def create(self, project_id: str, image_ids: List[str],
               replicate_training_id: Optional[str] = None,
               status: str = TrainingRun.STATUS_PENDING) -> TrainingRun:
        user_id = self._get_user_id()
        training_run_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        item = {
            'training_run_id': training_run_id,
            'project_id': str(project_id),
            'user_id': user_id,
            'image_ids': image_ids or [],
            'status': status,
            'created_at': now,
            'updated_at': now,
        }
        if replicate_training_id is not None:
            item['replicate_training_id'] = replicate_training_id

        self._table().put_item(Item=item)
        return TrainingRun.from_dict(item)

    def get_by_id(self, training_run_id: str) -> TrainingRun:
        user_id = self._get_user_id()
        result = self._table().get_item(Key={'training_run_id': training_run_id})
        item = result.get('Item')
        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Training run with ID {training_run_id} not found.")
        return TrainingRun.from_dict(item)

    def get_by_replicate_id(self, replicate_training_id: str) -> Optional[TrainingRun]:
        user_id = self._get_user_id()
        result = self._table().query(
            IndexName='project_id-created_at-index',
            FilterExpression=Attr('user_id').eq(user_id) & Attr('replicate_training_id').eq(replicate_training_id),
        )
        items = result.get('Items', [])
        return TrainingRun.from_dict(items[0]) if items else None

    def get_draft_by_project(self, project_id: str) -> Optional[TrainingRun]:
        user_id = self._get_user_id()
        result = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(str(project_id)),
            FilterExpression=Attr('user_id').eq(user_id) & Attr('status').eq(TrainingRun.STATUS_DRAFT),
        )
        items = result.get('Items', [])
        return TrainingRun.from_dict(items[0]) if items else None

    def get_or_create_draft(self, project_id: str) -> TrainingRun:
        existing = self.get_draft_by_project(project_id)
        if existing:
            return existing
        return self.create(project_id=project_id, image_ids=[], status=TrainingRun.STATUS_DRAFT)

    def add_images_to_run(self, training_run_id: str, image_ids: List[str]) -> TrainingRun:
        if not image_ids:
            return self.get_by_id(training_run_id)
        run = self.get_by_id(training_run_id)
        user_id = self._get_user_id()
        updated = list(set(run.image_ids or []) | set(image_ids))
        self._table().update_item(
            Key={'training_run_id': training_run_id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET image_ids = :ids, updated_at = :now',
            ExpressionAttributeValues={':ids': updated, ':now': datetime.utcnow().isoformat()},
        )
        return self.get_by_id(training_run_id)

    def add_images_to_draft(self, project_id: str, image_ids: List[str]) -> TrainingRun:
        draft = self.get_or_create_draft(project_id)
        return self.add_images_to_run(draft.id, image_ids)

    def replace_images(self, training_run_id: str, image_ids: List[str]) -> TrainingRun:
        user_id = self._get_user_id()
        self._table().update_item(
            Key={'training_run_id': training_run_id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET image_ids = :ids, updated_at = :now',
            ExpressionAttributeValues={':ids': image_ids, ':now': datetime.utcnow().isoformat()},
        )
        return self.get_by_id(training_run_id)

    def remove_images_from_draft(self, project_id: str, image_ids: List[str]) -> Optional[TrainingRun]:
        if not image_ids:
            return self.get_draft_by_project(project_id)
        draft = self.get_draft_by_project(project_id)
        if not draft:
            return None
        user_id = self._get_user_id()
        remove_set = set(image_ids)
        updated = [i for i in (draft.image_ids or []) if i not in remove_set]
        self._table().update_item(
            Key={'training_run_id': draft.id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET image_ids = :ids, updated_at = :now',
            ExpressionAttributeValues={':ids': updated, ':now': datetime.utcnow().isoformat()},
        )
        return self.get_by_id(draft.id)

    def list_by_project(self, project_id: str) -> List[TrainingRun]:
        user_id = self._get_user_id()
        result = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(str(project_id)),
            FilterExpression=Attr('user_id').eq(user_id),
            ScanIndexForward=False,
        )
        return [TrainingRun.from_dict(item) for item in result.get('Items', [])]

    def update_status(self, training_run_id: str, status: str,
                      error_message: Optional[str] = None) -> TrainingRun:
        if status not in TrainingRun.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {TrainingRun.VALID_STATUSES}")
        user_id = self._get_user_id()
        now = datetime.utcnow().isoformat()
        expr_parts = ['#st = :status', 'updated_at = :now']
        vals = {':status': status, ':now': now}
        if status in [TrainingRun.STATUS_SUCCEEDED, TrainingRun.STATUS_FAILED, TrainingRun.STATUS_CANCELED]:
            expr_parts.append('completed_at = :now')
        if error_message is not None:
            expr_parts.append('error_message = :err')
            vals[':err'] = error_message
        self._table().update_item(
            Key={'training_run_id': training_run_id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET ' + ', '.join(expr_parts),
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues=vals,
        )
        return self.get_by_id(training_run_id)

    def set_replicate_id(self, training_run_id: str, replicate_training_id: str) -> TrainingRun:
        user_id = self._get_user_id()
        self._table().update_item(
            Key={'training_run_id': training_run_id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET replicate_training_id = :rid, updated_at = :now',
            ExpressionAttributeValues={
                ':rid': replicate_training_id,
                ':now': datetime.utcnow().isoformat(),
            },
        )
        return self.get_by_id(training_run_id)

    def delete(self, training_run_id: str) -> None:
        user_id = self._get_user_id()
        item = self._table().get_item(Key={'training_run_id': training_run_id}).get('Item')
        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Training run with ID {training_run_id} not found.")
        self._table().delete_item(Key={'training_run_id': training_run_id})

    def delete_by_project(self, project_id: str) -> int:
        user_id = self._get_user_id()
        result = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(str(project_id)),
            FilterExpression=Attr('user_id').eq(user_id),
        )
        items = result.get('Items', [])
        with self._table().batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'training_run_id': item['training_run_id']})
        return len(items)
