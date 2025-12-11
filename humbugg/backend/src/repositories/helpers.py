from typing import Any, Dict, List

from bson import ObjectId


def normalize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
  """Convert MongoDB _id/ObjectId to string Id for API responses."""
  normalized = dict(doc)
  object_id = normalized.pop('_id', None)
  if isinstance(object_id, ObjectId):
    normalized['Id'] = str(object_id)
  return normalized


def normalize_many(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
  return [normalize_document(doc) for doc in docs]
