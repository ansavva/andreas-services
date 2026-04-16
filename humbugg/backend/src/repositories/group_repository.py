import os
import uuid
from typing import List, Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

from src.repositories.helpers import normalize_document, normalize_many

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')


class GroupRepository:
  # db_name is accepted but unused — kept for backward compatibility with existing route instantiation
  def __init__(self, db_name: str = None):
    pass

  def _table(self):
    return dynamodb.Table(os.environ['HUMBUGG_GROUPS_TABLE'])

  def list_ids_for_user(self, group_ids: List[str]) -> List[dict]:
    if not group_ids:
      return []
    keys = [{'group_id': gid} for gid in group_ids]
    resp = dynamodb.batch_get_item(
      RequestItems={
        os.environ['HUMBUGG_GROUPS_TABLE']: {'Keys': keys}
      }
    )
    items = resp['Responses'].get(os.environ['HUMBUGG_GROUPS_TABLE'], [])
    return normalize_many(items)

  def get(self, group_id: str) -> Optional[dict]:
    resp = self._table().get_item(Key={'group_id': group_id})
    item = resp.get('Item')
    return normalize_document(item) if item else None

  def create(self, group_doc: dict) -> dict:
    group_id = str(uuid.uuid4())
    item = {'group_id': group_id, **group_doc}
    self._table().put_item(Item=item)
    return normalize_document(item)

  def update(self, group_id: str, group_doc: dict) -> None:
    item = {'group_id': group_id, **group_doc}
    self._table().put_item(Item=item)

  def delete(self, group_id: str) -> None:
    self._table().delete_item(Key={'group_id': group_id})
