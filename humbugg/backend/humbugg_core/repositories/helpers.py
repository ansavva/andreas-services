from typing import Any, Dict, List


def normalize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
  """Return a shallow copy of a DynamoDB item, adding 'Id' from the item's primary key if present."""
  if doc is None:
    return None
  normalized = dict(doc)
  # Expose the primary-key field as 'Id' so callers that expect 'Id' continue to work.
  for pk_field in ('member_id', 'group_id', 'user_id'):
    if pk_field in normalized and 'Id' not in normalized:
      normalized['Id'] = normalized[pk_field]
      break
  return normalized


def normalize_many(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
  return [normalize_document(doc) for doc in docs]
