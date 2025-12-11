from typing import List, Optional

from bson import ObjectId

from src.extensions import get_db
from src.repositories.helpers import normalize_document, normalize_many


class GroupMemberRepository:
  def __init__(self, db_name: str):
    self.collection = get_db(db_name).groupmembers

  def get_by_user(self, user_id: str) -> List[dict]:
    docs = list(self.collection.find({'UserId': user_id}))
    return normalize_many(docs)

  def get_by_group(self, group_id: str) -> List[dict]:
    docs = list(self.collection.find({'GroupId': group_id}))
    return normalize_many(docs)

  def get_by_user_and_group(self, user_id: str, group_id: str) -> Optional[dict]:
    doc = self.collection.find_one({'UserId': user_id, 'GroupId': group_id})
    return normalize_document(doc) if doc else None

  def get(self, member_id: str) -> Optional[dict]:
    doc = self.collection.find_one({'_id': ObjectId(member_id)})
    return normalize_document(doc) if doc else None

  def create_many(self, docs: List[dict]) -> None:
    self.collection.insert_many(docs)

  def create(self, doc: dict) -> dict:
    result = self.collection.insert_one(doc)
    return self.get(str(result.inserted_id))

  def update(self, member_id: str, doc: dict) -> None:
    self.collection.replace_one({'_id': ObjectId(member_id)}, doc)

  def update_recipient(self, member_id: str, recipient_id: str | None) -> None:
    self.collection.update_one({'_id': ObjectId(member_id)}, {'$set': {'RecipientId': recipient_id}})

  def delete(self, member_id: str) -> None:
    self.collection.delete_one({'_id': ObjectId(member_id)})

  def delete_by_group(self, group_id: str) -> None:
    self.collection.delete_many({'GroupId': group_id})
