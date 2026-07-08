import os

from humbugg_core.app_factory import app


if __name__ == '__main__':
  os.environ.setdefault('AWS_ACCESS_KEY_ID', 'local')
  os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'local')
  os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
  os.environ.setdefault('DYNAMODB_ENDPOINT_URL', 'http://localhost:8001')
  os.environ.setdefault('HUMBUGG_PROFILES_TABLE', 'humbugg-profiles')
  os.environ.setdefault('HUMBUGG_GROUPS_TABLE', 'humbugg-groups')
  os.environ.setdefault('HUMBUGG_GROUPMEMBERS_TABLE', 'humbugg-groupmembers')

  from humbugg_core.repositories.dynamodb import ensure_local_tables_exist

  ensure_local_tables_exist()
  env = os.getenv('APP_ENV', 'development')
  debug_mode = env == 'development'
  app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', '5001')))
