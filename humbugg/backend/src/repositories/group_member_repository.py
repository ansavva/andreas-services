import os
import uuid
from typing import List, Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

from src.repositories.helpers import normalize_document, normalize_many

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')


class GroupMemberRepository:
  # db_name is accepted but unused — kept for backward compatibility with existing route instantiation
  def __init__(self, db_name: str = None):
    pass

  def _table(self):
    return dynamodb.Table(os.environ['HUMBUGG_GROUPMEMBERS_TABLE'])

  def get_by_user(self, user_id: str) -> List[dict]:
    resp = self._table().query(
      IndexName='user_id-index',
      KeyConditionExpression=Key('user_id').eq(user_id)
    )
    return normalize_many(resp['Items'])

  def get_by_group(self, group_id: str) -> List[dict]:
    resp = self._table().query(
      IndexName='group_id-index',
      KeyConditionExpression=Key('group_id').eq(group_id)
    )
    return normalize_many(resp['Items'])

  def get_by_user_and_group(self, user_id: str, group_id: str) -> Optional[dict]:
    # Query user_id-index then filter by group_id
    resp = self._table().query(
      IndexName='user_id-index',
      KeyConditionExpression=Key('user_id').eq(user_id),
      FilterExpression=Attr('group_id').eq(group_id)
    )
    items = resp['Items']
    return normalize_document(items[0]) if items else None

  def get(self, member_id: str) -> Optional[dict]:
    resp = self._table().get_item(Key={'member_id': member_id})
    item = resp.get('Item')
    return normalize_document(item) if item else None

  def create_many(self, docs: List[dict]) -> None:
    with self._table().batch_writer() as batch:
      for doc in docs:
        member_id = str(uuid.uuid4())
        # Derive lowercase GSI key fields from the uppercase payload fields
        user_id = doc.get('UserId') or doc.get('user_id', '')
        group_id = doc.get('GroupId') or doc.get('group_id', '')
        item = {
          'member_id': member_id,
          'user_id': user_id,
          'group_id': group_id,
          **doc
        }
        batch.put_item(Item=item)

  def create(self, doc: dict) -> dict:
    member_id = str(uuid.uuid4())
    # Derive lowercase GSI key fields from the uppercase payload fields
    user_id = doc.get('UserId') or doc.get('user_id', '')
    group_id = doc.get('GroupId') or doc.get('group_id', '')
    item = {
      'member_id': member_id,
      'user_id': user_id,
      'group_id': group_id,
      **doc
    }
    self._table().put_item(Item=item)
    return normalize_document(item)

  def update(self, member_id: str, doc: dict) -> None:
    # Derive lowercase GSI key fields from the uppercase payload fields
    user_id = doc.get('UserId') or doc.get('user_id', '')
    group_id = doc.get('GroupId') or doc.get('group_id', '')
    item = {
      'member_id': member_id,
      'user_id': user_id,
      'group_id': group_id,
      **doc
    }
    self._table().put_item(Item=item)

  def update_recipient(self, member_id: str, recipient_id: Optional[str]) -> None:
    update_expr = 'SET RecipientId = :val'
    expr_values = {':val': recipient_id}
    self._table().update_item(
      Key={'member_id': member_id},
      UpdateExpression=update_expr,
      ExpressionAttributeValues=expr_values
    )

  def delete(self, member_id: str) -> None:
    self._table().delete_item(Key={'member_id': member_id})

  def delete_by_group(self, group_id: str) -> None:
    resp = self._table().query(
      IndexName='group_id-index',
      KeyConditionExpression=Key('group_id').eq(group_id)
    )
    with self._table().batch_writer() as batch:
      for item in resp['Items']:
        batch.delete_item(Key={'member_id': item['member_id']})
