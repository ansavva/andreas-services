import os

import boto3
from botocore.exceptions import ClientError

from src import config

_dynamodb = None

_LOCAL_TABLES = {
  'HUMBUGG_PROFILES_TABLE': {
    'hash': ('user_id', 'S'),
  },
  'HUMBUGG_GROUPS_TABLE': {
    'hash': ('group_id', 'S'),
  },
  'HUMBUGG_GROUPMEMBERS_TABLE': {
    'hash': ('member_id', 'S'),
    'gsis': [
      ('user_id-index', ('user_id', 'S')),
      ('group_id-index', ('group_id', 'S')),
    ],
  },
}


def _region():
  return (
    os.environ.get('AWS_REGION')
    or os.environ.get('AWS_DEFAULT_REGION')
    or 'us-east-1'
  )


def resource():
  global _dynamodb
  if _dynamodb is None:
    kwargs = {'region_name': _region()}
    endpoint_url = config.dynamodb_endpoint_url()
    if endpoint_url:
      kwargs['endpoint_url'] = endpoint_url
    _dynamodb = boto3.resource('dynamodb', **kwargs)
  return _dynamodb


def table(env_var: str):
  return resource().Table(os.environ[env_var])


def batch_get_item(*args, **kwargs):
  return resource().batch_get_item(*args, **kwargs)


def ensure_local_tables_exist():
  for env_var, spec in _LOCAL_TABLES.items():
    _ensure_table(env_var, spec)


def _ensure_table(env_var, spec):
  table_name = os.environ[env_var]
  existing = resource().Table(table_name)
  try:
    existing.load()
    return
  except ClientError as exc:
    if exc.response.get('Error', {}).get('Code') != 'ResourceNotFoundException':
      raise

  hash_name, hash_type = spec['hash']
  attr_types = {hash_name: hash_type}
  gsis = []
  for index_name, gsi_hash in spec.get('gsis', []):
    gsi_hash_name, gsi_hash_type = gsi_hash
    attr_types[gsi_hash_name] = gsi_hash_type
    gsis.append({
      'IndexName': index_name,
      'KeySchema': [{'AttributeName': gsi_hash_name, 'KeyType': 'HASH'}],
      'Projection': {'ProjectionType': 'ALL'},
    })

  kwargs = {
    'TableName': table_name,
    'KeySchema': [{'AttributeName': hash_name, 'KeyType': 'HASH'}],
    'AttributeDefinitions': [
      {'AttributeName': name, 'AttributeType': attr_type}
      for name, attr_type in attr_types.items()
    ],
    'BillingMode': 'PAY_PER_REQUEST',
  }
  if gsis:
    kwargs['GlobalSecondaryIndexes'] = gsis
  created = resource().create_table(**kwargs)
  created.wait_until_exists()
