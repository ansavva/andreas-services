from typing import List, Optional

from bson import ObjectId

from src.extensions import get_db
from src.repositories.helpers import normalize_document, normalize_many


class GroupRepository:
  def __init__(self, db_name: str):
    self.collection = get_db(db_name).groups

  def list_ids_for_user(self, group_ids: List[str]) -> List[dict]:
    docs = list(self.collection.find({'_id': {'$in': [ObjectId(gid) for gid in group_ids]}}))
    return normalize_many(docs)

  def get(self, group_id: str) -> Optional[dict]:
    doc = self.collection.find_one({'_id': ObjectId(group_id)})
    return normalize_document(doc) if doc else None

  def create(self, group_doc: dict) -> dict:
    result = self.collection.insert_one(group_doc)
    return self.get(str(result.inserted_id))

  def update(self, group_id: str, group_doc: dict) -> None:
    self.collection.replace_one({'_id': ObjectId(group_id)}, group_doc)

  def delete(self, group_id: str) -> None:
    self.collection.delete_one({'_id': ObjectId(group_id)})
