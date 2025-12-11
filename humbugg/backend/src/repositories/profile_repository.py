from typing import Optional

from bson import ObjectId

from src.extensions import get_db
from src.repositories.helpers import normalize_document


class ProfileRepository:
  def __init__(self, db_name: str):
    self.collection = get_db(db_name).profiles

  def get(self, profile_id: str) -> Optional[dict]:
    doc = self.collection.find_one({'_id': ObjectId(profile_id)})
    return normalize_document(doc) if doc else None

  def create(self, profile: dict) -> dict:
    result = self.collection.insert_one(profile)
    return self.get(str(result.inserted_id))

  def update(self, profile_id: str, profile: dict) -> None:
    self.collection.replace_one({'_id': ObjectId(profile_id)}, profile)

  def delete(self, profile_id: str) -> None:
    self.collection.delete_one({'_id': ObjectId(profile_id)})
