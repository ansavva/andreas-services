import os
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

from src.repositories.helpers import normalize_document

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')


class ProfileRepository:
  # db_name is accepted but unused — kept for backward compatibility with existing route instantiation
  def __init__(self, db_name: str = None):
    pass

  def _table(self):
    return dynamodb.Table(os.environ['HUMBUGG_PROFILES_TABLE'])

  def get(self, user_id: str) -> Optional[dict]:
    resp = self._table().get_item(Key={'user_id': user_id})
    item = resp.get('Item')
    return normalize_document(item) if item else None

  def create(self, profile: dict) -> dict:
    # user_id must be present in the payload (comes from Cognito via the service layer)
    user_id = profile.get('user_id') or profile.get('UserId')
    if not user_id:
      raise ValueError('user_id is required to create a profile')
    item = {'user_id': user_id, **profile}
    self._table().put_item(Item=item)
    return normalize_document(item)

  def update(self, user_id: str, profile: dict) -> None:
    item = {'user_id': user_id, **profile}
    self._table().put_item(Item=item)

  def delete(self, user_id: str) -> None:
    self._table().delete_item(Key={'user_id': user_id})
