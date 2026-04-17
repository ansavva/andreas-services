from flask import request
from typing import List, Optional
import uuid
from datetime import datetime

from boto3.dynamodb.conditions import Key, Attr
from src.repositories.db.database import _table
from src.models.generation_history import GenerationHistory


class GenerationHistoryRepo:
    """
    Generation History repository.
    Table: STORYBOOK_GENERATION_HISTORY_TABLE  PK: generation_id (S)
    GSI:   project_id-created_at-index  PK: project_id (S), SK: created_at (S)
    """

    def _get_user_id(self) -> str:
        return request.cognito_claims['sub']

    @staticmethod
    def _table():
        return _table('STORYBOOK_GENERATION_HISTORY_TABLE')

    def create(self, project_id: str, prompt: str, image_ids: List[str],
               reference_image_ids: List[str] = None,
               status: str = GenerationHistory.STATUS_COMPLETED,
               include_subject_description: Optional[bool] = None,
               prediction_id: Optional[str] = None,
               provider: Optional[str] = None,
               error_message: Optional[str] = None) -> GenerationHistory:
        user_id = self._get_user_id()
        history_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        item = {
            'generation_id': history_id,
            'project_id': str(project_id),
            'user_id': user_id,
            'prompt': prompt,
            'image_ids': image_ids or [],
            'reference_image_ids': reference_image_ids or [],
            'status': status,
            'created_at': now,
            'updated_at': now,
        }
        if include_subject_description is not None:
            item['include_subject_description'] = include_subject_description
        if prediction_id is not None:
            item['prediction_id'] = prediction_id
        if provider is not None:
            item['provider'] = provider
        if error_message is not None:
            item['error_message'] = error_message

        self._table().put_item(Item=item)
        return GenerationHistory.from_dict(item)

    def get_by_id(self, history_id: str) -> GenerationHistory:
        user_id = self._get_user_id()
        result = self._table().get_item(Key={'generation_id': history_id})
        item = result.get('Item')
        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Generation history with ID {history_id} not found.")
        return GenerationHistory.from_dict(item)

    def get_draft_by_project(self, project_id: str) -> Optional[GenerationHistory]:
        user_id = self._get_user_id()
        result = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(str(project_id)),
            FilterExpression=Attr('user_id').eq(user_id) & Attr('status').eq(GenerationHistory.STATUS_DRAFT),
        )
        items = result.get('Items', [])
        return GenerationHistory.from_dict(items[0]) if items else None

    def get_or_create_draft(self, project_id: str) -> GenerationHistory:
        existing = self.get_draft_by_project(project_id)
        if existing:
            return existing
        return self.create(
            project_id=project_id,
            prompt='',
            image_ids=[],
            reference_image_ids=[],
            status=GenerationHistory.STATUS_DRAFT,
        )

    def add_reference_images_to_draft(self, project_id: str, image_ids: List[str]) -> GenerationHistory:
        if not image_ids:
            return self.get_or_create_draft(project_id)
        draft = self.get_or_create_draft(project_id)
        user_id = self._get_user_id()
        updated = list(set(draft.reference_image_ids or []) | set(image_ids))
        self._table().update_item(
            Key={'generation_id': draft.id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET reference_image_ids = :ids, updated_at = :now',
            ExpressionAttributeValues={':ids': updated, ':now': datetime.utcnow().isoformat()},
        )
        return self.get_by_id(draft.id)

    def remove_reference_images_from_draft(self, project_id: str, image_ids: List[str]) -> Optional[GenerationHistory]:
        if not image_ids:
            return self.get_draft_by_project(project_id)
        draft = self.get_draft_by_project(project_id)
        if not draft:
            return None
        user_id = self._get_user_id()
        remove_set = set(image_ids)
        updated = [i for i in (draft.reference_image_ids or []) if i not in remove_set]
        self._table().update_item(
            Key={'generation_id': draft.id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET reference_image_ids = :ids, updated_at = :now',
            ExpressionAttributeValues={':ids': updated, ':now': datetime.utcnow().isoformat()},
        )
        return self.get_by_id(draft.id)

    def finalize_draft(self, draft_id: str, prompt: str, image_ids: List[str],
                       reference_image_ids: Optional[List[str]] = None,
                       include_subject_description: Optional[bool] = None) -> GenerationHistory:
        user_id = self._get_user_id()
        now = datetime.utcnow().isoformat()
        expr_parts = ['prompt = :prompt', 'image_ids = :image_ids',
                      '#st = :status', 'created_at = :now', 'updated_at = :now']
        vals = {':prompt': prompt, ':image_ids': image_ids,
                ':status': GenerationHistory.STATUS_COMPLETED, ':now': now}
        if reference_image_ids is not None:
            expr_parts.append('reference_image_ids = :ref_ids')
            vals[':ref_ids'] = reference_image_ids
        if include_subject_description is not None:
            expr_parts.append('include_subject_description = :isd')
            vals[':isd'] = include_subject_description
        self._table().update_item(
            Key={'generation_id': draft_id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET ' + ', '.join(expr_parts),
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues=vals,
        )
        return self.get_by_id(draft_id)

    def promote_draft_to_processing(self, draft_id: str, prompt: str,
                                    reference_image_ids: Optional[List[str]] = None,
                                    include_subject_description: Optional[bool] = None,
                                    prediction_id: Optional[str] = None,
                                    provider: Optional[str] = None) -> GenerationHistory:
        user_id = self._get_user_id()
        now = datetime.utcnow().isoformat()
        expr_parts = ['prompt = :prompt', 'image_ids = :empty', '#st = :status',
                      'created_at = :now', 'updated_at = :now',
                      'prediction_id = :pred', 'provider = :prov']
        vals = {':prompt': prompt, ':empty': [], ':status': GenerationHistory.STATUS_PROCESSING,
                ':now': now, ':pred': prediction_id or '', ':prov': provider or ''}
        if reference_image_ids is not None:
            expr_parts.append('reference_image_ids = :ref_ids')
            vals[':ref_ids'] = reference_image_ids
        if include_subject_description is not None:
            expr_parts.append('include_subject_description = :isd')
            vals[':isd'] = include_subject_description
        self._table().update_item(
            Key={'generation_id': draft_id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET ' + ', '.join(expr_parts),
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues=vals,
        )
        return self.get_by_id(draft_id)

    def update_status(self, history_id: str, status: str,
                      image_ids: Optional[List[str]] = None,
                      error_message: Optional[str] = None) -> GenerationHistory:
        user_id = self._get_user_id()
        expr_parts = ['#st = :status', 'updated_at = :now']
        vals = {':status': status, ':now': datetime.utcnow().isoformat()}
        if image_ids is not None:
            expr_parts.append('image_ids = :image_ids')
            vals[':image_ids'] = image_ids
        if error_message is not None:
            expr_parts.append('error_message = :err')
            vals[':err'] = error_message
        self._table().update_item(
            Key={'generation_id': history_id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET ' + ', '.join(expr_parts),
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues=vals,
        )
        return self.get_by_id(history_id)

    def update_draft_prompt(self, project_id: str, prompt: str,
                            include_subject_description: Optional[bool] = None) -> GenerationHistory:
        draft = self.get_or_create_draft(project_id)
        user_id = self._get_user_id()
        expr_parts = ['prompt = :prompt', 'updated_at = :now']
        vals = {':prompt': prompt, ':now': datetime.utcnow().isoformat()}
        if include_subject_description is not None:
            expr_parts.append('include_subject_description = :isd')
            vals[':isd'] = include_subject_description
        self._table().update_item(
            Key={'generation_id': draft.id},
            ConditionExpression=Attr('user_id').eq(user_id),
            UpdateExpression='SET ' + ', '.join(expr_parts),
            ExpressionAttributeValues=vals,
        )
        return self.get_by_id(draft.id)

    def list_by_project(self, project_id: str, include_drafts: bool = False) -> List[GenerationHistory]:
        user_id = self._get_user_id()
        filter_expr = Attr('user_id').eq(user_id)
        if not include_drafts:
            filter_expr = filter_expr & Attr('status').ne(GenerationHistory.STATUS_DRAFT)
        result = self._table().query(
            IndexName='project_id-created_at-index',
            KeyConditionExpression=Key('project_id').eq(str(project_id)),
            FilterExpression=filter_expr,
            ScanIndexForward=False,
        )
        return [GenerationHistory.from_dict(item) for item in result.get('Items', [])]

    def delete(self, history_id: str) -> bool:
        user_id = self._get_user_id()
        item = self._table().get_item(Key={'generation_id': history_id}).get('Item')
        if not item or item.get('user_id') != user_id:
            raise ValueError(f"Generation history with ID {history_id} not found.")
        self._table().delete_item(Key={'generation_id': history_id})
        return True

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
                batch.delete_item(Key={'generation_id': item['generation_id']})
        return len(items)
