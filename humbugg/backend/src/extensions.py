from pymongo import MongoClient

mongo_client: MongoClient | None = None


def init_mongo(uri: str) -> None:
  """Initialise the global MongoClient instance."""
  global mongo_client
  if mongo_client is None:
    mongo_client = MongoClient(uri)


def get_db(db_name: str):
  if mongo_client is None:
    raise RuntimeError('Mongo client has not been initialised.')
  return mongo_client[db_name]
